# Maelin — See what breaks before you fix it. Remember what happened last time.

> **Graph Hacks Hackathon Submission** (WeMakeDevs × FalkorDB)  
> **Tracks Entered:** Track 01 (Connected Data) & Track 02 (Agent Memory and Coordination)

---

## The Problem
When a security alert fires, the standard response is emergency containment—quarantine or shut down the compromised service. But in modern distributed architectures, that often causes an immediate self-inflicted outage (for example, taking down an authentication service breaks checkout and billing).

Worse, AI agents often repeat the exact same operational mistake next week because they have no persistent memory of previous containment outcomes.

## What Maelin Does
Maelin is an incident-response decision engine built on **FalkorDB**:
1. **Discovers all multi-hop attack routes:** Uses Cypher graph traversal to find every privilege path connecting an entry point to sensitive data through a compromised component, while separately mapping customer business dependencies.
2. **Evaluates two counterfactual futures:** Compares **Future A** (emergency quarantine = high business outage) against **Future B** (surgical graph cut = zero customer impact).
3. **Replays actions on disposable graph clones:** Uses FalkorDB's native `Graph.copy()` to clone the topology, execute candidate edge/node cuts in Cypher, re-traverse the modified clone, and verify that 100% of attack paths are severed before recommending an intervention.
4. **Remembers past outages across sessions:** When an operator reports that an intervention caused an unexpected outage, Maelin persists the outcome in an isolated FalkorDB memory graph (`Episode -> ActionExperience`). In future sessions, Maelin automatically penalizes that action and recommends a safer alternative.

---

## Why FalkorDB is Indispensable (Rule #3 Litmus Test)
* **Zero in-memory fallbacks:** Production code has no local JSON, NetworkX, or in-memory graph traversal fallbacks.
* **Fails closed:** If FalkorDB is offline or unreachable, the API immediately returns **HTTP 503**. 
* **Native Graph Clone & Replay:** Disposable simulations mutate isolated FalkorDB graph clones directly in Cypher, leaving the live topology untouched.

---

## How It Solves Both Tracks

| Track | What FalkorDB Powers | How to Verify It |
|---|---|---|
| **Track 01: Connected Data** | Multi-hop Cypher queries (`CAN_PIVOT*1..7` & `DEPENDS_ON*1..7`) find dangerous paths that `shortestPath()` misses due to benign shortcuts. Evaluates surgical graph cuts against customer blast radius. | Click **Investigate**. See two independent attack routes. Run **Replay** to see FalkorDB cut edges on a clone and reduce remaining paths from 2 to 0. |
| **Track 02: Agent Memory & Coordination** | Specialists (`Recon`, `Memory`, `Remediation`) coordinate via immutable `Session -> Handoff` nodes in FalkorDB. Episodic and procedural memory penalizes failed actions across sessions. | Click **Report unexpected outage** on an action → start a **New Session** → recommendation switches to a safer alternative. Switch tenant (`alpha` vs `beta`) to verify strict isolation. |

---

## Architecture & Multi-Agent Flow

```text
                        FALKORDB (Tenant-Isolated Graphs)
                ┌────────────────────────────────────────────────┐
                │  Topology Graph          Swarm Memory Graph    │
                │  • Asset Nodes           • Session Nodes       │
                │  • CAN_PIVOT Edges       • Handoff Ledgers     │
                │  • DEPENDS_ON Edges      • Episode / Outcomes  │
                └───────▲──────────────────────────▲─────────────┘
                        │                          │
                        │ Multi-hop Cypher         │ Reads/Writes Handoffs
                        │                          │
  ┌─────────────────────┴──────────────────────────┴─────────────────────────┐
  │                                                                           │
  │  1. Recon Agent       ──► Mapped threat paths & business dependencies    │
  │                           (persists handoff into FalkorDB)                │
  │                                                                           │
  │  2. Memory Agent      ──► Recalls prior incident outcomes by fingerprint  │
  │                           & component (persists handoff into FalkorDB)    │
  │                                                                           │
  │  3. Remediation Agent ──► Formulates complete graph cut, compares blast   │
  │                           radius, and checks memory ablation              │
  │                                                                           │
  └─────────────────────────────────────┬────────────────────────────────────┘
                                        │
                         Optional LLM Tool Adjudication
                     (Google Gemini / OpenAI function calling)
                                        │
                                        ▼
                           Interactive Web UI / FastMCP
```

---

## Quickstart (Run in 2 Minutes)

### 1. Start with Docker Compose
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

## 75-Second Judge Demo Walkthrough

1. **Investigate the Incident:**
   Click **▶ Investigate incident**. An attacker can reach `customer-db` from `auth-service` via two privilege paths (`vault-sync` and `admin-role`).
2. **Compare the Two Futures:**
   * **Future A (Emergency quarantine):** 160 business impact units (checkout and order sync broken).
   * **Future B (Selected surgical cut):** 0 business impact units (cuts only pivots, keeping customer flows live).
3. **Replay on FalkorDB Clone:**
   Click **◈ Replay selected plan in FalkorDB**. Maelin creates an ephemeral graph copy, applies the deletions in Cypher, re-traverses the graph, and confirms: **Remaining threat routes: 0**.
4. **Test Persistent Memory & Adaptation:**
   Click **⚑ Report unexpected outage** on `revoke-admin-role`. Then click **↺ Start a new session**.
   * The **Memory Agent** recalls the failure from FalkorDB.
   * Look at the **Memory Causal Test** card: with memory active, the decision switches to `rotate-auth-credentials`.
5. **Inject Adversarial Drift:**
   Click **⚡ Inject shadow route**. A hidden third attacker pivot is written to FalkorDB.
   * Click **Investigate**: the old 2-cut plan is no longer sufficient! Maelin adapts its cut strategy to cover the new path.
6. **Verify Tenant Isolation:**
   Switch to **Tenant Beta** in the top dropdown. The memory from Tenant Alpha does not leak.

---

## Automated Judge Verification Harness (1 Command)

You can run the full, self-contained verification suite on any running FalkorDB instance:

```bash
python -m maelin.judge --output judge-proof.json
```

**What this harness verifies in ~10 seconds:**
- Creates a randomized, disposable test tenant.
- Runs cold investigation → verifies 2 threat paths found.
- Simulates plan replay on a cloned graph → verifies 0 remaining routes.
- Stores an outage outcome in episodic memory → runs a new session → verifies recommendation changes.
- Injects a shadow route drift → verifies older plan invalidation.
- Automatically cleans up and deletes test graphs.

---

## Core Cypher Queries

### 1. Bounded Multi-Hop Attack Traversal (`maelin/store.py`)
```cypher
MATCH p=(s:Asset {id:$source})-[:CAN_PIVOT*1..7]->(t:Asset {id:$target})
WITH p WHERE ANY(n IN nodes(p) WHERE n.id = $vulnerable)
RETURN [n IN nodes(p) | n.id] AS assets,
       [r IN relationships(p) | r.edge_id] AS pivots LIMIT 257
```
*Why this matters:* `shortestPath()` can be deceived by benign shortcuts that bypass the compromised node. This query guarantees finding all danger paths up to 7 hops.

### 2. Business Dependency Traversal (`maelin/store.py`)
```cypher
MATCH p=(f:Asset)-[:DEPENDS_ON*1..7]->(s:Asset)
WHERE f.kind='business_flow'
RETURN f.id, f.value, [n IN nodes(p) | n.id] LIMIT 1025
```

### 3. Episodic Memory Recall (`maelin/store.py`)
```cypher
MATCH (e:Episode {fingerprint:$fingerprint})-[:OBSERVED]->(a:ActionExperience)
RETURN a.action_id, a.outcome, a.cost_observed, a.evidence_status, e.created, e.id
ORDER BY e.created DESC LIMIT 30
```

---

## Optional LLM Agent Mode (Gemini & OpenAI)

Maelin runs in deterministic policy mode by default. To enable model-powered analytical insight synthesis and function-calling plan adjudication:

```bash
pip install -r requirements-agent.txt

# Set Gemini or OpenAI API key:
export GEMINI_API_KEY="<your-gemini-key>"
# or: export OPENAI_API_KEY="<your-openai-key>"

export MAELIN_USE_LLM=1
```

*Note: The LLM cannot invent graph edges, generate arbitrary Cypher, or execute cloud commands. It strictly analyzes and selects among graph-verified complete plans.*

---

## FastMCP Server

Maelin includes a built-in stdio FastMCP server exposing typed graph tools (`inspect_attack_paths`, `inspect_business_dependencies`, `recall_incident_outcomes`, `list_candidate_interventions`, `propose_containment`):

```bash
python -m maelin.mcp_server
```

---

## Test Suite

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```
* **47 offline and invariant tests pass in ~3 seconds.**
* Includes an exhaustive property-based oracle checking 600 random graph configurations.

---

## References & Disclosure

* [Official Hackathon Details](https://www.wemakedevs.org/hackathons/falkordb)
* [FalkorDB Official Python Client](https://github.com/FalkorDB/falkordb-py)
* [FalkorDB MCP Server](https://github.com/FalkorDB/falkordb-mcp)
* *AI Assistance Disclosure:* AI coding assistance was used during the prototyping and testing of this submission. All architecture, graph queries, invariants, and tests were reviewed, debugged, and verified by the authors.
