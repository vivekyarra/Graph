# Maelin | Judge-proof evidence packet | Oct 16, 2026

**One sentence:** Maelin uses a graph to find *every modeled threat route*, proposes a graph-cut intervention, mutates a disposable FalkorDB graph to check whether that cut works, and remembers outcome reports across sessions. The same topology is re-evaluated *with and without memory* to show exactly when memory changed the decision.

## Exact entries (both tracks)

- **Agents That Act on Connected Data**: The key decision comes from FalkorDB's `CAN_PIVOT` and `DEPENDS_ON` traversals, the graph-defined interventions, and replay on FalkorDB's native copied graph. A shortest benign route must not hide a longer vulnerable one. Incomplete cuts are refused.
- **Agent Memory and Coordination**: Recon persists path evidence as a `Handoff` attached to a `Session`; Memory *reads* that handoff, queries previous `Episode → ActionExperience` records, and persists another handoff; Remediation *reads* both handoffs and produces a plan. Persistent memory can alter its action. A controlled ablation computes a fresh policy from the *same graph* with just the reports removed; the result is displayed in the UI and returned in the API.

## One command: verify or falsify every central claim

On a machine with FalkorDB running (e.g., `docker compose up -d graph`):

```bash
python -m pip install -r requirements-dev.txt
python -m maelin.judge --output judge-proof.json
```

The command uses a **random, temporary synthetic tenant graph**. It fails on any unmet assertion, deletes both temporary tenant graphs on exit and prints evidence in JSON. It does not modify a real cloud account or execute infrastructure commands.

Check the `maelin-dual-track-evidence` artifact on the successful GitHub Actions run: the CI executes this command against the **real** FalkorDB server, not an in-memory mock. `FALKOR_INTEGRATION=1 python -m pytest -q` also exercises live Cypher, concurrent handoffs, copy/delete, replay, drift, and tenant-specific memories.

## The 75-second judge sequence

1. **Graph falsification**: `internet → auth-service → admin-role/vault-sync → customer-db` has two independent 7-hop-bounded danger routes even though the graph has a shorter benign bypass. Show the actual source-query Cypher.
2. **Future fork**: Naïve quarantine costs 160 **synthetic impact units**. The complete surgical cut costs 0 modeled customer impact (base intervention cost 5). Run clone replay: graph route count **2 → 0**. A one-sided cut leaves **1** still open.
3. **Prove memory causality**: Make a clearly labeled *synthetic operator report* for `revoke-admin-role`, start a new session. The graph-stored outcome is recalled; the decision changes. Show the blue/orange **Without memory / With memory** comparison, built from the same topology/actions. This is evidence that the *decision policy* used memory, **not** an independently verified real outage.
4. **Adversarial drift**: Introduce the synthetic `shadow-role` route. Replay the *old* intervention again: one dangerous path remains (**3 → 1**), so an outdated “safe” recommendation is no longer valid. The next investigation changes its plan based on FalkorDB's updated graph.

## Falsification and limits

| Claim | Objective test | Boundary |
|---|---|---|
| Multi-hop matters | Live Cypher returns longer vulnerable paths despite a shorter bypass | At most 7 hops and 256 enumerated threat paths |
| Graph is load-bearing | Remove/stop FalkorDB: API returns 503 instead of a synthetic answer | No local JSON source in production |
| Counterfactual is not pretend | Native graph copy, Cypher edge/node deletion, re-query, cleanup | Synthetic graph, no cloud actions |
| Memory changes a decision | Same graph/actions cold vs warm ablation shows different recommended action | Input experience is an operator report, not forensic proof |
| Multi-agent coordination is durable | Separate graph-stored handoffs and deterministic specialists | Not three independent autonomous LLMs; model arbitration is optional |
| Tampering is constrained | Write and graph-read protection outside local demo, tenant graph separation | Single operator token, not enterprise RBAC |
| Cost optimizer is bounded | Oracle fuzzing + explicit cap at 48 actions | No assertion of global optimality beyond 3 interventions or unseen topology |

## What makes this more than the organizer's baseline tutorial?

**A new decision primitive:** Two futures are not merely displayed. Maelin has an auditable evidence chain: graph-constrained optimizer → disposable graph *mutation* → second graph traversal → durable multi-agent memory → controlled memory ablation → topology-drift invalidation. Every arrow can be checked with the API or the judge harness. It also refuses incomplete plans, invalid costs, duplicate action IDs, and oversized candidate sets instead of silently claiming safety.

## Official rules audit

- ✅ FalkorDB primary graph database and a real dependency of both pathways.
- ✅ Enter both Track 01 and Track 02; rules expressly permit multi-track entries.
- ✅ Public/synthetic graph data only; no personal or restricted data.
- ✅ Public source repository, explicit graph model, Cypher queries, Docker and setup commands.
- ✅ Disclose AI assistance. Human participant MUST review/understand source, validate official account/team eligibility, and meaningfully contribute; do not claim AI-only output meets this requirement.
- ⬜ Real demo video captured from a working FalkorDB instance, publicly accessible before submission.
- ⬜ Participant personally reruns verification and reviews every claim; confirms submission on official panel before Oct 18, 23:59 IST.
- ⬜ A live deployment is preferred, but the official rules accept complete local setup instructions.

**Not claimed:** a verified exploit, a quantified real business outage, a production security platform, autonomous cloud remediation, official judge scores, or any guarantee of winning.

Official rules: https://www.wemakedevs.org/hackathons/falkordb/rules
