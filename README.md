# Maelin — See what breaks before you fix what’s broken

**Graph Hacks: Context for AI Agents** (WeMakeDevs × FalkorDB, Oct 15–18, 2026)

**Pronunciation:** *MAY-lin.* Maelin is the AI incident-response companion that explores the consequences of proposed containment actions and remembers previous failures. **Tagline:** “See what breaks before you fix what’s broken.”

**Entering BOTH tracks:** (1) Agents That Act on Connected Data; (2) Agent Memory and Coordination.

> **The 15-second story:** An attacker can reach a customer database along *two* privilege paths. Shutting down the compromised authentication service stops the exposure but destroys checkout. MAELIN finds the cheapest complete graph cut, compares the two futures, and remembers when a previous containment action caused a surprise outage. The next session makes a different, safer recommendation. **Judge-verifiable twist:** a proposed intervention can be applied to a disposable FalkorDB graph clone and re-queried; a new hidden pivot makes yesterday's successful cut fail visibly.

This is a **real, source-code prototype**, not a claim that the system has been deployed or that the model can actually execute cloud remediation. It uses **synthetic assets**, **synthetic costs**, and **operator-reported simulation outcomes**. No real infrastructure is changed.

## Why Maelin is not a generic agent wrapper

| Track | Load-bearing functionality | Demonstrate it |
|---|---|---|
| Connected Data | FalkorDB Cypher enumerates bounded multi-hop `CAN_PIVOT` attack routes *through the vulnerable asset*, and separate customer `DEPENDS_ON` paths. A deterministic counterfactual engine refuses to recommend any action set leaving even one known threat path uncut. | Two independent routes, a tempting partial fix rejected, a dangerous quarantine option with high customer impact, and a low-disruption complete graph cut; the separate sandbox graph then executes that cut and re-queries the remaining routes. |
| Agent Memory and Coordination | Separate tenant-specific FalkorDB memory graphs hold `Session`, `Handoff`, `Episode`, `ActionExperience`, and proposed actions. Specialists **read the previous agent's persisted handoff** rather than passing Python state. Previous operator-reported failures affect next-session scores. | Record failed role revocation → start a new session → recommendation switches to rotating both credentials. Change tenant → memory does not leak. |

### The one truly important innovation

Most agents answer **“What happened?”** Maelin answers **“What will break if we do the obvious thing, and what did we learn the last time it went wrong?”**. It combines threat connectivity, service blast radius, counterfactual action-set planning, and outcome-aware persistent memory into one decision.

### Architecture

```text
                      FALKORDB — tenant-specific isolated graphs
                  ┌─────────────────┐  ┌───────────────────┐
Synthetic alert ─►│ topology graph  │  │ memory graph      │
                  │ Asset            │  │ Session           │
Recon agent ─────►│ CAN_PIVOT        │─►│ Handoff: paths    │
   (Cypher)       │ DEPENDS_ON       │  │ Handoff: recall   │
                  │ Intervention     │  │ Episode           │
                  └─────────────────┘  │ ActionExperience  │
                                        └─────────┬─────────┘
                                    Memory agent ◄┘
                                         │ persists recall
                                         ▼
                                 Remediation agent
                                 • fetch BOTH handoffs
                                 • choose complete graph cut
                                 • simulate business impact
                                 • penalize prior failures
                                         │
                            Optional OpenAI tool-choice arbitration
                            (bounded to safe approved plans)
                                         │
                             Web UI + read-only MCP tools
                                         │
                             Human reports outcome to memory
```

**No FalkorDB, no answer.** The production API has no local-JSON or NetworkX fallback. `logic.traversal_fallback()` is deliberately isolated in the **offline unit tests only**. An unreachable database returns HTTP 503 instead of pretending a result was computed.

## Run on your own computer (Docker Desktop, including Windows)

From the `maelin` directory:

```powershell
docker compose up --build -d
# Wait until the FalkorDB service has started:
docker compose exec app python -m maelin.seed --tenant alpha
docker compose exec app python -m maelin.seed --tenant beta
```

Open **http://localhost:8000** for MAELIN and **http://localhost:3000** for the FalkorDB graph browser. The FalkorDB wire protocol is on port 6379.

The first run starts with **no incident history**. Open the UI, click **Investigate incident**, inspect two vulnerable attack paths, and compare the default response to emergency quarantine. Click **Replay selected plan in FalkorDB** to create a temporary native graph clone, mutate its pivot edges and re-check routes; it will be deleted after the replay, with the result saved as a handoff. Then click **Report unexpected outage**, specifying `revoke-admin-role` when offered. Click **Start a new session** to observe a changed recommendation based on that recorded report. Next click **Inject shadow route**, which writes an additional synthetic attacker pivot to FalkorDB, and investigate again: the old two-edge fix and credential rotation no longer cut all three paths, so the agent must choose a different intervention. You can also replay the old session's action IDs via `/api/demo/simulate` and observe the remaining open path. Switch to Tenant Beta to check separation. To erase the demo data for one tenant, explicitly pass `--reset` to the seed module; note that doing so **deletes that tenant's two graphs**.

To shut down: `docker compose down`. To delete *all Docker-hosted persisted graph data*: `docker compose down -v` (destructive).

**Backend**: FastAPI `http://localhost:8000/docs` includes typed endpoints. `POST /api/investigate` returns bounded paths, the score breakdown for counterfactual plans, graph-memory precedents, and a durable handoff trace. `POST /api/demo/simulate` takes `{tenant, session_id, action_ids}` and, only in trusted demo mode, executes these on a disposable FalkorDB graph copy, re-traverses the modified copy, deletes it and persists the report in the memory graph. The real topology graph is never modified by replay.

### Optional model-powered agent choice

The safety reasoning runs deterministically so it is independently testable. An LLM is **optional** and cannot invent graph paths, issue Cypher or execute fixes. It can use a function tool to select among a narrow set of fully covering plans, with its output checked by a deterministic validator. Without it, the UI explicitly identifies `deterministic_policy` mode. With an LLM, it identifies `llm_tool_choice_validated` or an explicit unavailable fallback.

For model-powered mode, install the optional packages (adjust Dockerfile as needed) and set:

```bash
pip install -r requirements-agent.txt
export OPENAI_API_KEY="<your API key>"
export MAELIN_USE_LLM=1
# Local development: FALKOR_HOST=localhost uvicorn maelin.api:api --reload
```

For Docker Compose, set the environment variables on the **app** container and rebuild the image with `requirements-agent.txt`; the default Docker image installs only `requirements.txt` and therefore runs in deterministic mode. Do **not** commit API keys or record them in a demo.

### MCP server

With optional packages installed and FalkorDB started:

```bash
python -m maelin.mcp_server
```

The bridge exposes only typed, bounded `inspect_attack_paths`, `inspect_business_dependencies`, `recall_incident_outcomes`, and `propose_containment` tools. It exposes **no arbitrary Cypher execution** and **no actual infrastructure mutation**. Connect it as a stdio MCP server in your agent host.

## Critical graph model and Cypher

- Graphs are physically separated per tenant: `maelin_alpha_topology`, `maelin_alpha_memory`, etc. Tenant names are syntactically validated.
- Topology vertices: `(:Asset {id,kind,x,y,value,critical})` and `(:Intervention {id,blocked_nodes,blocked_edges,cost})`.
- Attack transitions: `(:Asset)-[:CAN_PIVOT {edge_id,evidence}]->(:Asset)`. **Synthetic assertions of possible transitions**, not verified exploitation.
- Customer dependency: `(:Asset)-[:DEPENDS_ON {edge_id,evidence}]->(:Asset)`.
- Memory: `(:Session)-[:HAS_HANDOFF]->(:Handoff)`; `(:Session)-[:PROPOSED]->(:ProposedAction)`; `(:Session)-[:RESULTED_IN]->(:Episode)-[:OBSERVED]->(:ActionExperience)`.

**Attack traversal** (production code in `maelin/store.py`):

```cypher
MATCH p=(s:Asset {id:$source})-[:CAN_PIVOT*1..7]->(t:Asset {id:$target})
WITH p WHERE ANY(n IN nodes(p) WHERE n.id = $vulnerable)
RETURN [n IN nodes(p) | n.id] AS assets,
       [r IN relationships(p) | r.edge_id] AS pivots LIMIT 257
```

Why not `shortestPath()` followed by a vulnerability filter? A shorter *benign* path can conceal a longer path through the compromised service. This seeded graph contains that exact adversarial counterexample. The benchmark tests that both dangerous routes are found without counting the benign shortcut.

**Customer dependency query:**

```cypher
MATCH p=(f:Asset)-[:DEPENDS_ON*1..7]->(s:Asset)
WHERE f.kind='business_flow'
RETURN f.id, f.value, [n IN nodes(p) | n.id] LIMIT 1025
```

**Memory recall query:**

```cypher
MATCH (e:Episode {fingerprint:$fingerprint})-[:OBSERVED]->(a:ActionExperience)
RETURN a.action_id, a.outcome, a.cost_observed,
       a.evidence_status, e.created, e.id
ORDER BY e.created DESC LIMIT 30
```

Only operator-reported outcomes are persisted in this prototype; they are labeled **operator_report**, not automatically verified real-world success or failure.

## Tests and empirical results

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Offline (available in the authoring environment) tests exercise the optimizer, a stand-in graph-store interface, and synthetic graph reachability. A separately written exhaustive oracle probes **600 random cases** to ensure the optimizer always matches the oracle's minimum cost, including when previous failures alter the score. The unit tests cannot establish that FalkorDB executes every Cypher pattern correctly.

For a real integration smoke test after Docker starts:

```bash
# Windows PowerShell:
$env:FALKOR_INTEGRATION="1"
python -m pytest -q tests/test_live_falkordb.py

# Or inside the Docker app container (pytest is not in the default image):
# pip install -r requirements-dev.txt before running
```

A GitHub Actions workflow at `.github/workflows/falkordb-integration.yml` starts a real FalkorDB service, runs all tests with `FALKOR_INTEGRATION=1`, emits failed-container logs, and tears down the service. **This CI configuration is authored, not yet executed in a published repository.**

The real smoke test creates only the dedicated `maelin_ci_alpha_*` and `maelin_ci_beta_*` graphs, clears those dedicated test graphs, verifies actual Cypher results, performs and cleans up database-native graph-copy intervention replays, persists handoffs and outcomes, verifies idempotency and tenant isolation, and injects a third path to invalidate a previously valid containment plan.

**Current verified result in this package:** 24 offline tests passed, two live integration tests skipped because no FalkorDB server was available in the authoring environment. **No live FalkorDB Cypher correctness, Docker startup, or submission eligibility is claimed as tested yet.**

## How to demo it in ~3 minutes

1. **0:00–0:25** “A compromised login component has two routes to the production database. The obvious containment action is expensive.” Show topology and two red routes.
2. **0:25–0:55** Click investigate. Show the two independent vulnerable paths and a partial intervention rejected because it leaves one route open. **Replay a real graph copy**, showing `2 → 0` paths after the surgical cut.
3. **0:55–1:30** Show Future A (quarantine auth, synthetic 160 impact units) versus Future B (surgical cut, 0 modeled customer-flow impact). Switch plans and show highlighted cuts.
4. **1:30–2:15** Report a synthetic unexpected outage for the role revocation intervention. Start a **new session**. Memory agent retrieves the incident and the remediation plan switches to credential rotation. Show the actual `Session → Handoff` graph in FalkorDB Browser.
5. **2:15–2:45** Click **Inject shadow route**. A third synthetic attacker route appears. Replay the old session plan to show `3 → 1` still-open threat path, then investigate again to choose a different graph-dependent plan. Then switch to Tenant Beta to confirm its memory is isolated.
6. **2:45–3:00** Show the FalkorDB Browser's stored session/handoff nodes. Close with: “The agent cannot act without a graph, cannot recommend an incomplete intervention, and does not forget what its earlier decision cost.”

**Don't fake the demo**: run with FalkorDB, not screenshots, and label synthetic outcomes. Recording a failure is not an actual infrastructure fault-injection experiment.

## Important limitations and honest future work

- Threat edges model *plausible* attacker transitions supplied by the synthetic dataset. They are not proofs that a real attacker has met preconditions. Real connectors, IAM semantics, and evidence provenance are future work.
- The bounded Cypher query stops at 7 hops. 257+ threat paths or 1025+ business paths trigger refusal, but a path beyond the depth limit could still exist. **Do not infer actual safety from a negative result.**
- Interventions are implemented as Cypher `DELETE` operations on an isolated FalkorDB graph clone, then verified by a fresh graph traversal; the clone is deleted. Scoring uses illustrative, uncalibrated impact units. The project does **not** execute real revocations, quarantines, or credential changes.
- The `Inject shadow route` endpoint is enabled **only in the included trusted LOCAL Docker demo** using `MAELIN_ENABLE_DEMO_MUTATIONS=1`. Disable that variable in public deployments. Graph-writing APIs **fail closed by default**. The bundled Docker Compose binds all ports to `127.0.0.1` and explicitly sets `MAELIN_LOCAL_DEMO=1` to permit the local interactive demo. For any remote deployment unset `MAELIN_LOCAL_DEMO`, set a strong `MAELIN_OPERATOR_TOKEN`, disable `MAELIN_ENABLE_DEMO_MUTATIONS`, and terminate TLS at a trusted proxy. This is a prototype with a single operator token, not a complete production multi-user RBAC solution.
- No benchmark against competing Graph Hacks entries exists; **no claim of winning is warranted yet**.
- Live FalkorDB test remains **mandatory** before submission; Docker and optional-model behavior were not end-to-end verified here.
- AI coding assistance helped build this prototype. **Disclose this in the submission**; participants must review, test, and understand the code themselves.

## Submission compliance checklist

- [ ] Confirm registration and actual team name (1–4 members) on the official site.
- [x] Specify both targeted tracks in docs.
- [x] Include schema and dependency-defining Cypher queries.
- [x] Use only synthetic data in the demo.
- [ ] Run and record real FalkorDB integration tests (workflow provided but not executed).
- [ ] Confirm fresh `docker compose up --build` works from a clean machine.
- [ ] Publish a public source repository once you approve it.
- [ ] Record a real working video and include a live deployment or tested local instructions.
- [ ] Publish README, architecture, documented benchmarks and AI assistance disclosure.
- [ ] Submit by **Oct 18, 2026, 11:59 PM IST**.

### Key organizers/sponsor references

- [Official hackathon challenge](https://www.wemakedevs.org/hackathons/falkordb)
- [Official rules](https://www.wemakedevs.org/hackathons/falkordb/rules)
- [Organizer tutorial — Blast Radius](https://www.wemakedevs.org/blogs/how-to-build-an-agent-that-reasons-over-a-graph) — **intentionally differentiated from** this example.
- [FalkorDB sponsor winners/standouts](https://www.falkordb.com/blog/memory-meets-motion-the-falkordb-standouts/)
- [Official FalkorDB Python client](https://github.com/FalkorDB/falkordb-py)
- [Official FalkorDB MCP server](https://github.com/FalkorDB/falkordb-mcp)

Copyright remains yours/your team’s under the hackathon rules; no external competitor's source code is copied into this project. Choose your preferred license before publishing.

## Hardening notes (October 16)

- Graph writes (including investigation session creation) now fail closed unless a matching `MAELIN_OPERATOR_TOKEN` header is supplied, or the explicitly local and loopback-bound `MAELIN_LOCAL_DEMO=1` configuration is used. Read-only endpoints remain accessible; do not expose unrestricted graph browsing in sensitive deployments.
- `POST /api/outcome` treats the initial operator outcome per session/action as immutable: conflicting retries return HTTP 409 instead of falsely claiming the new value was saved. Matching retries are idempotent.
- Local Compose binds FalkorDB and the demo web app to 127.0.0.1; do not bind Docker ports publicly or reuse local-demo overrides in deployed infrastructure.
- Stored reports are operator assertions, never automatically verified forensic evidence. The source's synthetic impact numbers are illustrative.
