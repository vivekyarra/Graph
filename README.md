# MAELIN — Graph-native incident response time machine

**See what breaks before you fix it. Remember what happened last time.**

Maelin investigates a synthetic cyber incident, enumerates *all bounded attack paths* with FalkorDB Cypher, reasons about interventions with real read-only MCP graph tools, and simulates the impact on a **disposable FalkorDB graph clone**. A second incident can reuse operator-reported experience from an isolated graph memory and explain why its decision changed.

**Hackathon:** [Graph Hacks: Context for AI Agents — WeMakeDevs × FalkorDB](https://www.wemakedevs.org/hackathons/falkordb) (October 15–18, 2026). **Tracks:** 01 — Agents That Act on Connected Data, 02 — Agent Memory and Coordination.

## Five-minute judge journey

1. Run the Docker Compose stack and seed tenant Alpha and Beta (commands below). Visit http://localhost:8000.
2. Investigate the demo: two compromised routes reach the customer database; the selected surgical pair blocks both without taking customer flows offline.
3. Inspect the MCP tool ledger, verified Cypher path payloads, counterfactual cut and business-impact meter. Replay the cut in a disposable FalkorDB clone.
4. Report a *synthetic* failed action and start a new session. The graph-linked prior incident changes the proposed intervention. Switch to Beta to verify tenant isolation.
5. Inject a synthetic shadow route: the previous plan no longer contains the incident, and new graph queries drive a different proposal.
6. Choose another source/pivot/target directly from the graph. Expand **Load a custom synthetic infrastructure graph** to import another JSON scenario into a NEW FalkorDB tenant.

The browser is an interactive, draggable force-layout incident cockpit. It does not compute reachability or remember incidents in JavaScript: all authoritative graph data, memory and simulation state stay in FalkorDB.

## Architecture

    Browser — FastAPI operator boundary
        |
        +--> Session-scoped three-agent pipeline
        |       Recon — MCP: inspect_attack_paths / inspect_business_dependencies
        |       Memory — MCP: recall_incident_outcomes / inspect_business_dependencies
        |       Remediation — MCP: list_candidate_interventions
        |                      + admissible plan tool-choice
        |       [Each specialist can initiate additional LLM-selected read-only
        |        graph tool calls; the app enforces tenant and incident arguments]
        |
        +--> FalkorDB tenant topology graph — authoritative assets, pivots,
        |       business dependencies, interventions, scenario metadata
        |
        +--> FalkorDB tenant memory graph — session, handoffs, episodes,
                procedures, incident patterns, semantic patterns,
                conversation turns and provenance

### Why the graph is indispensable

FalkorDB computes bounded paths using Cypher variable-length traversals. The simulation makes a **native graph copy**, deletes the proposed edges/nodes in that copy, and **re-runs** Cypher to determine remaining attack reachability. The memory agent reads persisted graph relationships; no SQLite/JSON/in-memory path-finder exists in production. Remove FalkorDB and the API cannot investigate, remember, simulate or produce graph-derived candidate plans.

Key graph queries (implemented in [store.py](maelin/store.py)):

    MATCH p=(s:Asset {id:$source})-[:CAN_PIVOT*1..7]->(t:Asset {id:$target})
    WITH p WHERE ANY(n IN nodes(p) WHERE n.id=$vulnerable)
    RETURN [n IN nodes(p)|n.id], [r IN relationships(p)|r.edge_id] LIMIT 257

    MATCH p=(f:Asset)-[:DEPENDS_ON*1..7]->(s:Asset)
    WHERE f.kind='business_flow'
    RETURN f.id, f.value, [n IN nodes(p)|n.id] LIMIT 1025

    MATCH (p:IncidentPattern {fingerprint:$fingerprint})
       -[:HAS_EPISODE]->(e:Episode)-[:OBSERVED]->(a:ActionExperience)
    RETURN a.action_id, a.outcome, a.cost_observed, a.evidence_status, e.created, e.id

    MATCH (k:SemanticPattern {key:$key})
       -[:REMEMBERS]->(e:Episode)-[:OBSERVED]->(a:ActionExperience)
    RETURN a.action_id, a.outcome, a.cost_observed, a.evidence_status, e.created, e.id

The deterministic kernel **never chooses an intervention that leaves a known bounded threat route open**. It enumerates at most 48 candidate interventions in combinations of up to three, accounts for modeled lost business flows, and penalizes historical operator-reported damage. Uncertain or excessive path counts fail closed. This is an explanation of a bounded synthetic graph, not proof that a real infrastructure deployment is secure.

### Episodic, semantic and procedural memory

- **Episodic:** immutable tenant-scoped Episode → OBSERVED → ActionExperience records, with timestamps, evidence status, and cost.
- **Semantic:** SemanticPattern nodes keyed by *asset roles/kinds* connect related incident episodes. Similar-but-not-identical incidents receive only 25% of reported-loss weight; action IDs must match current candidate actions.
- **Procedural:** IncidentPattern → HAS_PROCEDURE → Procedure → SUPPORTED_BY → ActionExperience. Outcome reports create review procedures tied to source evidence.
- **Conversation and coordination:** Session → HAS_TURN → ConversationTurn preserves operator goal and assistant recommendation; Session → HAS_HANDOFF → Handoff preserves each specialist's verified evidence and every MCP stdio tool trace.
- **Isolation:** each tenant has its own topology and memory graphs, with session-bound action authorization and immutable outcome reports.

### What makes these agents real?

When a model is configured, all **three specialist agents** can request typed read-only graph tools in a bounded LLM loop (at most three rounds). Tool calls execute against real FalkorDB through MCP stdio; model-supplied IDs, tenant names, and arbitrary Cypher are discarded. The remediation model then selects only among deterministically admissible graph-cut candidates through a validated function tool. The UI labels the model mode and exposes call traces.

If **no** model API or Ollama-compatible endpoint is configured, the safe deterministic policy still works and is labeled accurately. MCP graph tools remain active in Docker Compose. The README makes no claim that a model ran when one did not.

## Run locally — real FalkorDB

Prerequisite: Docker with Compose.

    git clone https://github.com/vivekyarra/Graph.git
    cd Graph
    docker compose up -d --build
    docker compose exec -T app python -m maelin.seed --tenant alpha
    docker compose exec -T app python -m maelin.seed --tenant beta

Open **http://127.0.0.1:8000**. The Compose service is bound to localhost and uses explicit local-demo mode. Never expose that exact configuration to the public internet.

### Enable LLM agent reasoning

Option A — OpenAI compatible hosted provider: set an API key in your local .env file and run:

    OPENAI_API_KEY=<your private key>
    MAELIN_USE_LLM=auto
    MAELIN_LLM_MODEL=gpt-4o-mini

Option B — local Ollama (with an installed tool-capable model):

    MAELIN_LLM_BASE_URL=http://host.docker.internal:11434/v1
    MAELIN_LLM_MODEL=<your installed tool-capable model>
    MAELIN_USE_LLM=auto

Do not commit credentials. Hosted model access is optional for running the deterministic safety proof, but **required to demonstrate live language-model reasoning**. Tool-loop evidence is recorded per session and can be inspected in the UI.

## Import a second incident (not hardcoded to auth-service)

The original synthetic dataset is [data/demo.json](data/demo.json). You can import up to 120 assets, 240 edges and 48 interventions from your own synthetic JSON, with required fields:

- Top-level: \`scenario\`, \`fingerprint\`, \`source\`, \`vulnerable\`, \`target\`, \`assets\`, \`pivot_edges\`, \`depends_edges\`, \`actions\`.
- Asset: \`id\`, \`kind\` (ingress/service/identity/database/business_flow), optional \`x\`, \`y\`, \`value\`, \`critical\`.
- Edge: \`id\`, \`from\`, \`to\`, optional \`evidence\`. Intervention: \`id\`, \`label\`, \`cost\`, \`blocked_nodes\`, \`blocked_edges\`, optional \`note\`.

The validator checks endpoint references, unique IDs, action catalogs, bounded graph size and numeric costs. POST \`/api/scenarios\` seeds **only a new tenant**; it never silently overwrites existing graph data. You may also use:

    python -m maelin.seed --tenant fresh_case --file custom-scenario.json

You can use \`POST /api/investigate\` with \`tenant\`, \`goal\`, \`source\`, \`vulnerable\`, \`target\`, \`alert\`; source/pivot/target are checked against live FalkorDB assets. Trace endpoints: \`GET /api/trace/{session_id}\` and \`GET /api/conversation/{session_id}\`.

## Validation and reproducibility

GitHub Actions are configured for real FalkorDB/Cypher integration, isolation, concurrent sessions, 5,000 randomized optimizer/oracle cases, executable judge evidence, Dockerized FastAPI, actual Playwright/Chromium screenshots and a WebM recording. The standalone demo container additionally has a smoke workflow that runs its own FalkorDB process; it must also be green before submission. Status of each run is available in [Actions](https://github.com/vivekyarra/Graph/actions). Artifacts are uploaded as \`maelin-dual-track-evidence\` and \`maelin-real-browser-proof\`.

    docker compose up -d graph
    pip install -r requirements-dev.txt -r requirements.txt
    FALKOR_INTEGRATION=1 python -m pytest -q
    python -m maelin.judge --output judge-proof.json

For Windows PowerShell set \`$env:FALKOR_INTEGRATION="1"\` before running pytest. The standalone demo uses \`Dockerfile.demo\`: it runs **the real FalkorDB engine inside the same container**, but its data are **ephemeral across host shutdown/redeploy**. Docker Compose or hosted FalkorDB is needed for durable memory across process restarts.

## Deployment and security

Two supported deployment modes:

- **Public one-container demo**: build \`Dockerfile.demo\` as a Docker web service, set a long random \`MAELIN_OPERATOR_TOKEN\`. The only public socket is FastAPI HTTP; FalkorDB listens on loopback. Suitable for a temporary synthetic hackathon demo.
- **Durable hosting**: use \`Dockerfile\` with external FalkorDB Cloud. Set \`FALKOR_HOST\`, \`FALKOR_PORT\`, \`FALKOR_USERNAME\`, \`FALKOR_PASSWORD\`, \`FALKOR_SSL=1\` and \`MAELIN_OPERATOR_TOKEN\` through the deployment platform's secret manager. Example infrastructure is in [render.yaml](render.yaml).

Never enable \`MAELIN_LOCAL_DEMO=1\` on a public service. Use HTTPS/TLS and the operator token for all protected API calls. Database connections are authenticated where appropriate, and simulated cuts never call real infrastructure services. User-uploaded graph information must be synthetic or owned/authorized.

## Submission materials

Read [JUDGE_PACKET.md](JUDGE_PACKET.md) for traceable Track 01/02 evidence and honest scope; [SUBMISSION_VIDEO_AND_JUDGE_QA.md](SUBMISSION_VIDEO_AND_JUDGE_QA.md) for a working-video recording plan; and [VALIDATION_STATUS.md](VALIDATION_STATUS.md) for the test matrix.

**AI-assistance disclosure:** ChatGPT / OpenAI AI coding assistance was used for code generation, graph/query implementation, tests, documentation, architecture review and debugging. The participant(s) must verify and understand the code, record the real demo, and submit it themselves. See competition Rule 11 and Rule 13. Do not present generated code without participant verification.
