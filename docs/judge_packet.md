# Maelin — judge evidence packet

**Track 01: Agents That Act on Connected Data. Track 02: Agent Memory and Coordination.**

## What to show live

Start the Docker Compose or hosted demo and demonstrate **a real FalkorDB query for the paths**, **an actual MCP tool call**, **an authenticated scene selection**, **the cut applied to a copied graph**, and **a repeated incident whose policy changes because of persisted graph experience**.

### Track 01 — what the graph does

Each Recon query uses FalkorDB Cypher to find paths from entry to target passing through the selected compromised asset (depth <=7, max 256 records). A separate query finds business-flow dependencies (max 1024). Remediation enumerates every bounded action combination and refuses those that leave a known compromised route uncovered. Replaying an action creates a new FalkorDB graph, makes Cypher DELETE modifications, and independently queries reachable paths after the change. A newly injected pivot must make the old cut incomplete.

**Demonstration:** first incident returns two paths; a surgical pair cuts both, while blanket quarantine interrupts modeled customer flows. Inject the shadow route and repeat: three paths now exist. User can also choose a different node or import an entirely separate synthetic topology.

### Track 01 — agents and MCP

In Docker Compose and the standalone demo, Recon/Memory/Remediation use `MAELIN_AGENT_TOOLS=mcp`: typed stdio tool invocations, with recorded `mcp / tool_called` handoffs. With an OpenAI-compatible model configured, each specialist can select which read-only graph tool to query, and Remediation makes a separately checked function-tool selection among allowed interventions. The model cannot execute arbitrary Cypher or push actual infrastructure changes. If the model isn't configured, the UI says so.

### Track 02 — persistent graph context

- `Session` → `HAS_HANDOFF` → `Handoff`: all graph-driven agent communications and MCP calls.
- `Session` → `HAS_TURN` → `ConversationTurn`: operator goal/alert and assistant response.
- `IncidentPattern` → `HAS_EPISODE` → `Episode` → `OBSERVED` → `ActionExperience`: sourced episodic memory.
- `IncidentPattern` → `HAS_PROCEDURE` → `Procedure` → `SUPPORTED_BY` → `ActionExperience`: procedural review constraints.
- `SemanticPattern` → `REMEMBERS` → `Episode`: bounded generalization by asset kind/role.

Compare the same current graph with and without memory to establish whether the decision change is explained by past operator reports. Show tenant Beta with no leaked Alpha memory. Graphs are scoped to tenants and outcomes to actual offered session actions.

### Inspect tests rather than screenshots alone

GitHub Actions has three concrete evidence channels:

1. **Python test + live FalkorDB workflow:** Cypher, graph copy, memory isolation, concurrent sessions, randomized oracle, Docker API and Chromium.
2. **Judge replay harness:** `python -m maelin.judge --output judge-proof.json` proves cold → replay → memory → drift on disposable actual graphs.
3. **Standalone demo image:** `Dockerfile.demo` starts the FalkorDB engine and API in one container and tests authenticated MCP calls.

Inspect the current Actions runs. CI passing validates the tested graph operations; it does *not* mean a model-provider account has been configured, nor does it replace a demo video.

## Compliance and honesty

FalkorDB is the **primary and only runtime graph database**. The pure-Python traversal oracle is under `tests/` only. All demo topology and incidents are synthetic. No unauthorized real-world remediation or private user data are involved. The project's AI coding assistance is disclosed in README. A public deployed service is preferred but the hackathon also permits complete local setup instructions when deployment is impossible.

**Remaining human submission actions** (not claims of automated completion): participant confirms hackathon registration/team, verifies AI-model credential if presenting an LLM demonstration, records/hosts a real video, provides the final URL and submits before October 18, 2026 11:59 PM IST.

## Judge Q&A

**What happens when FalkorDB disappears?** Every query, memory operation and simulation fails closed. The frontend is not a pathfinder. The DFS oracle used by unit tests lives under `tests/`.

**Are they really agents?** With credentials, separate Recon, Memory and Remediation specialists select restricted graph tools through a bounded LLM loop and persist reasoning/handoff context. Without model credentials, the same safety kernel is intentionally deterministic and labeled as such.

**Is memory just a numerical penalty?** Decision ranking includes a cost-sensitive penalty, but its evidence is retrieved through real episodic, semantic-pattern and procedural FalkorDB subgraphs; live memory ablation shows the causal influence. Similar kinds get discounted evidence weights.

**Can I change the graph?** Yes. Choose any valid source/pivot/target, or import a separate synthetic graph with new interventions into a fresh tenant using the JSON importer.

**Can this change production systems?** No. The only mutations are synthetic topology injection, episode recording and disposable database clone simulation, behind an operator-authenticated boundary.

**What's left after a green CI?** Record and upload a real presentation video; verify the chosen model provider is working; register and submit the project on WeMakeDevs. For a durable public service supply a hosted FalkorDB connection; the bundled web demo is ephemeral.
