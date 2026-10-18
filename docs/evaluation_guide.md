# MAELIN — System Verification & Empirical Evaluation Guide

This guide details the mathematical invariants, graph database mechanics, and empirical verification harnesses underlying MAELIN (Multi-Agent Episodic Learning Incident Network).

---

## 1. Architectural Verification Overview

MAELIN uses **FalkorDB** as its sole shared state and graph reasoning engine. Every investigation, counterfactual simulation, memory retrieval, and agent handoff executes native Cypher queries against FalkorDB.

| Verification Dimension | Mechanism | Formal Guarantee |
|---|---|---|
| **Threat Route Completeness** | Variable-length Cypher traversal (`*1..7`) with `nodes(p)` and `relationships(p)` provenance | Zero truncated paths up to depth 7; bounded complexity with limit refusal if `> 256` paths exist |
| **Provable Minimal Cut** | Native `algo.maxFlow` (Edmonds-Karp / Dinic) over unit-capacity `CAN_PIVOT` relations | Menger's Theorem guarantee: maximum flow equals the minimum pivot cut separating compromised node from target |
| **Blast Radius & Downstream Dependency** | Reverse traversal over `DEPENDS_ON` relations mapped to revenue and customer flows | Exact financial and operational impact quantification ($k/h revenue interruption) |
| **Downstream Centrality** | Native PageRank (`CALL algo.pageRank('Asset', 'DEPENDS_ON')`) | Ranks critical infrastructure assets by structural business centrality |
| **Zero-Side-Effect Counterfactual Simulation** | Native `Graph.copy()` creating `maelin_{tenant}_sim_{uuid}` | True disposable state: mutations (`DELETE`) are replayed on the cloned graph and verified without altering live topologies |
| **Zero-In-Memory Agent Coordination** | Immutable `(:Session)-[:HAS_HANDOFF]->(:Handoff)` graph nodes | Distributed agents pass state strictly through graph persistence, not Python in-memory references |
| **Multi-Tenant State Isolation** | Graph namespacing (`maelin_{tenant}_*`) with regex validation | Strict tenant boundaries: Tenant Alpha queries and memories cannot observe or contaminate Tenant Beta |

---

## 2. Core Capabilities & Formal Proofs

### Capability 1: Agents That Act on Connected Data
* **Hop-by-Hop Provenance**: Recon queries return both `nodes(p)` and `relationships(p)` in a single atomic transaction. The UI and MCP tools render exact edge evidence strings (e.g. `CVE-2024-4577`, `SSRF-AWS-IMDSv2`, `Kubelet-Exec`).
* **Why Bounded Traversal Beats Shortest Path**: In adversarial security contexts, `shortestPath()` is fundamentally unsound—benign shortcuts mask stealthier multi-hop lateral pivots. MAELIN enumerates all acyclic paths through the compromised asset up to depth 7.
* **Deterministic Pareto Optimization**: Remediation evaluates the full power set of candidate interventions (up to $2^{12}$ combinations), eliminating any candidate plan that leaves even one threat route unblocked. The remaining valid plans are Pareto-ranked by customer continuity and remediation cost.

### Capability 2: Episodic, Semantic, and Procedural Memory
* **Multi-Layered Memory Graph**:
  * **Episodic**: `(:IncidentPattern)-[:HAS_EPISODE]->(:Episode)-[:OBSERVED]->(:ActionExperience)` stores historical operational outcomes.
  * **Semantic**: `(:SemanticPattern)-[:REMEMBERS]->(:Episode)` enables categorical generalization when structurally similar incidents occur across different services.
  * **Procedural**: `(:Procedure)-[:SUPPORTED_BY]->(:ActionExperience)` captures runbook constraints and organizational policy guidelines.
* **Live Causal Ablation**: When an operator records an unexpected outage (e.g. revoking a role broke a production database pool), MAELIN computes the decision *with* and *without* historical memory. If past experience alters the recommendation, MAELIN exposes a causal ablation report identifying the specific historical episode and operator rationale.

### Capability 3: Company Brain (Organizational Knowledge Subgraph)
* **Unified Enterprise Topology**: Connects technical services directly to organizational reality:
  * `(:Team {id, name, lead, contact})-[:OWNS]->(:Asset {id})`
  * `(:Person {name, on_call})-[:MEMBER_OF]->(:Team)`
  * `(:Document {kind: 'runbook'|'postmortem'|'adr'})-[:ABOUT]->(:Asset)`
  * `(:Decision)-[:DECIDED_BY]->(:Person)`
* **Grounded Question Answering**: Questions posed to the Brain perform full-text indexing (`CALL db.idx.fulltext.queryNodes('Document', $query)`) combined with ownership subgraph traversal, returning answers with exact document citations, accountable team leads, and active on-call responders.

---

## 3. Automated Test Suite & Verification Harnesses

The repository includes a comprehensive, multi-layered verification harness executable in automated CI or local development:

```bash
# 1. Execute full offline invariant and property-based test suite
pytest -q

# 2. Execute live FalkorDB integration suite (when running with live database)
FALKOR_INTEGRATION=1 pytest -q

# 3. Execute the full end-to-end empirical verification harness
python -m maelin.judge --output verification-proof.json

# 4. Execute headless Chromium end-to-end user journey
python tests/e2e_real_browser.py
```

### Key Automated Verification Checks:
1. **`test_invariants.py`**: Proves absence of in-memory graph fallbacks (no SQLite, NetworkX, or memory graph simulations). MAELIN strictly fails closed (`HTTP 503`) if FalkorDB is unreachable.
2. **`test_stress.py`**: Property-based oracle generating 5,000 synthetic random directed acyclic graphs and verifying that the FalkorDB Cypher output exactly matches the mathematical traversal oracle.
3. **`test_hardening.py`**: Proves constant-time token comparison, protection against timing attacks, and strict rejection of unauthorized requests on remote deployments.
4. **`test_simulation.py`**: Validates that concurrent counterfactual simulations run in isolated `Graph.copy()` instances with dynamic UUID suffixes and execute reliable `try...finally` graph deallocation.

---

## 4. Technical Architecture FAQ

#### What happens if the FalkorDB cluster is unavailable?
MAELIN fails closed immediately with `HTTP 503 Service Unavailable`. The system contains zero mock graph fallbacks or in-memory emulation kernels in production code. The pure-Python DFS traversal algorithm exists strictly under `tests/offline_graph.py` as a test oracle to verify Cypher invariants.

#### Are the agents autonomous or hardcoded scripts?
With API credentials provided (`OPENAI_API_KEY` or `GEMINI_API_KEY`), three independent specialist agents (Reconnaissance, Memory Recall, and Remediation) execute an LLM loop where they dynamically choose which typed MCP tools to query, pass structured handoffs through FalkorDB, and synthesize natural-language justifications. Without credentials, MAELIN executes the deterministic Pareto graph kernel directly, ensuring safe, verifiable operation under all deployment conditions.

#### How is multi-tenant isolation enforced?
Tenant graphs are completely segregated at the database catalog level: `maelin_{tenant}_topology` and `maelin_{tenant}_memory`. Cypher queries are parameterized and validate tenant identifiers against strict regular expressions. Historical incidents recorded in Tenant Alpha are mathematically invisible to Tenant Beta.

#### Does simulation mutate live infrastructure?
No. Simulations occur strictly within disposable FalkorDB clone graphs generated via `Graph.copy()`. Interventions (node detach-deletions and relationship deletions) are applied solely to the temporary clone, re-evaluated for path reachability, and immediately torn down via `graph.delete()`.
