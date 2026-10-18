# MAELIN — System Evaluation & Verification Packet

> **Note**: For the complete formal evaluation specification, mathematical invariants, and proofs, see the [Comprehensive Evaluation Guide](evaluation_guide.md).

---

## Technical Highlights by Capability Domain

### Domain 01 — Agents That Act on Connected Data
* **Real FalkorDB Graph Traversal**: Bounded multi-hop Cypher queries (`CAN_PIVOT*1..7`, depth up to 7, bounded limit) returning explicit `nodes(p)` and `relationships(p)` provenance.
* **Menger's Theorem Min-Cut**: Proves the mathematical optimality of the recommended cut via native `algo.maxFlow`.
* **Asset Centrality**: Ranks infrastructure business criticality via native `algo.pageRank('Asset', 'DEPENDS_ON')`.
* **Counterfactual Replay**: Proves containment on dynamic disposable graph clones created via `Graph.copy()`.

### Domain 02 — Agent Memory and Multi-Agent Coordination
* **Triple-Layer Memory Architecture**: Episodic (`:Episode`), Semantic (`:SemanticPattern`), and Procedural (`:Procedure`) subgraphs in FalkorDB.
* **Vector Similarity Recall**: Cosine vector indexing over incident embeddings (`db.idx.vector.queryNodes`) for structural incident retrieval.
* **Causal Policy Ablation**: Mathematically evaluates decision variance with and without historical operator feedback.
* **Zero-In-Memory Agent Handoffs**: Agents coordinate strictly through immutable graph transactions (`(:Session)-[:HAS_HANDOFF]->(:Handoff)`).
* **Multi-Tenant Graph Segregation**: Strict catalog isolation (`maelin_{tenant}_*`) prevents cross-tenant memory leakage.

### Domain 03 — Company Brain (Organizational Knowledge Subgraph)
* **Unified Enterprise Graph**: Integrates infrastructure assets, revenue dependencies, responsible engineering teams (`:Team`), on-call staff (`:Person`), ADRs, and postmortems (`:Document`).
* **Source-Grounded Answering**: Full-text Cypher search (`db.idx.fulltext.queryNodes`) combined with ownership graph traversals to provide instant, cited answers with accountable owners.

---

## Verification Test Harnesses

Inspect automated test executions rather than static claims:
1. **Offline Invariants Suite**: `pytest -q` (109 passed tests validating schema, business logic, Pareto pruning, invariant preservation, and GraphBLAS telemetry).
2. **Live FalkorDB Integration Suite**: `FALKOR_INTEGRATION=1 pytest -q` (all 122 tests verifying live Cypher execution, vector index creation, and clone operations).
3. **End-to-End Verification Pipeline**: `python -m maelin.judge --output verification-proof.json` (reproducible cold-start, clone replay, memory adaptation, and topology drift validation on real disposable graphs).
4. **Automated Browser Journey**: `python tests/e2e_real_browser.py` (real Chromium browser automation asserting zero layout shift and correct UI execution).

---

## Architectural Decisions & FAQ

**What occurs when FalkorDB is offline?**
All agent operations, graph traversals, and simulations fail closed (`HTTP 503 Service Unavailable`). MAELIN contains zero mock or in-memory graph fallbacks in production.

**How do agents interact with the graph?**
Agent specialists invoke typed Model Context Protocol (MCP) tools via stdio (`maelin/mcp_server.py`). The LLM is restricted to read-only queries and action selection; it cannot execute raw Cypher or alter infrastructure.

**How does memory influence remediation?**
Historical incident postmortems stored in FalkorDB provide empirical weights. If past incidents show an intervention caused unforeseen downtime, the Pareto optimization engine recalculates expected utility, and the UI presents an explicit causal ablation diff.
