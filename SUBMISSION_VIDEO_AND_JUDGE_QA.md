# Maelin — submission kit (Track 01 + Track 02)

**Do not submit a fake screen recording.** Record the actual browser connected to a running FalkorDB service and show the graph browser or a terminal query to establish authenticity. All topology, CVE, customer costs and failure outcomes in this prototype are **synthetic**.

## One-sentence pitch

Maelin is the incident-response time machine: it finds the threat paths, tests fixes in a disposable copy of the real graph, and remembers when a fix caused collateral damage so the next agent chooses differently.

## Suggested 180-second judges' video

| Time | On screen | What to say / verify |
|---|---|---|
| 0–15s | Maelin dashboard | “A compromised login component threatens a database. One obvious fix kills checkout.” |
| 15–40s | Run Investigate | Show two paths through compromised auth; note the *shorter benign path* is not the answer. The connection evidence comes from FalkorDB Cypher, not text search. |
| 40–65s | Compare emergency quarantine with surgical pair | 160 vs 0 *synthetic* customer-impact units. Show why one edge cut is insufficient. |
| 65–90s | Click **Replay selected plan in FalkorDB** | A disposable cloned graph is actually modified by Cypher `DELETE`, then queried again: 2 routes → 0. It is automatically deleted, leaving the source graph intact. |
| 90–118s | Report a synthetic unexpected outage of `revoke-admin-role`; then new session | Track 02: a new Session reads persisted Episode and ActionExperience; recommendation changes to `rotate-auth-credentials`. Show the persisted Recon → Memory → Remediator handoff chain. |
| 118–150s | Inject a synthetic shadow pivot, then new session | Now 3 paths. Replaying the *old* two-cut action set yields one still-open route; current investigation picks a different option. This demonstrates non-scripted dependence on graph state. |
| 150–166s | Change Alpha → Beta tenant | The failure memory is absent in Beta; the initial plan returns. Separate FalkorDB memory graphs, not prompt instruction separation. |
| 166–180s | FalkorDB Browser or terminal | Show `MATCH (s:Session)-[:HAS_HANDOFF]->(h:Handoff) RETURN s.id,h.agent,h.status LIMIT 10` on the tenant memory graph. End: “Remove FalkorDB and the agent cannot reconstruct its evidence or memory.” |

For the highest-confidence proof, keep both the UI and a command-line test run visible. A prettier video without real execution is worse than a plain credible one.

## Judge Q&A — difficult questions, precise answers

**Q: Why a graph instead of vector embeddings or a regular SQL table?**

Attack feasibility depends on multi-hop relationships and customer dependencies. FalkorDB finds complete bounded paths through the compromised node, retrieves decisions by incident episodes, stores handoffs, and clones the topology graph to verify graph cuts. A text search cannot directly replace any of those semantics.

**Q: Does this guarantee an attack is stopped?**

No. The graph is synthetic and incomplete by design. The engine checks only the provided `CAN_PIVOT` routes of at most 7 hops, refusing to draw conclusions if the path limit is exceeded. The dashboard explicitly states the scope. A live environment needs verified asset/IAM ingestion and a broader graph-reachability model.

**Q: Are those three agents just three LLM prompts?**

No. They are deterministic specialist roles with independent store calls and graph-persisted handoffs. An optional model chooses from already-validated candidate plans, but cannot create paths or bypass the containment filter. The honest description is **graph-native tool-using specialist agents with optional bounded LLM choice**, not autonomous production security bots.

**Q: What makes memory genuinely load-bearing?**

With an empty incident memory graph the cheapest surgical pair wins. Recording a failed revocation in Alpha adds a graph-stored Episode and ActionExperience. Starting a new session causes Memory to retrieve the reported failure, which changes Remediator's ranking. Beta's separate memory graph lacks the penalty and keeps the original recommendation.

**Q: What is the creative differentiator?**

A fault-injection **time machine** with *two interacting counterfactuals*: an alternative world created by FalkorDB Graph.copy + Cypher action replay, and a new future decision changed by persistent failure memory. The story is visually interpretable without knowing security acronyms.

**Q: Why not claim production-grade?**

Because no cloud connectors, independent outcome validation, authentication/authorization, or calibrated disruption model are shipped. Remediation changes exist only inside a disposable graph clone. These constraints keep the hackathon demo safe and its claims honest.

## Submission fields (copy and personalize)

**Project:** Maelin — Graph-native incident-response time machine  
**Tracks:** Agents That Act on Connected Data; Agent Memory and Coordination  
**Stack:** FalkorDB, Cypher, Graph.copy, Python, FastAPI, MCP, optional OpenAI tool selection, HTML/SVG dashboard  
**Data rights:** Fully synthetic  
**AI assistance:** AI coding assistant used in architecture, implementation, documentation and tests; participant(s) manually review and verify code and explain its technical decisions before submission  
**Repository:** [ADD PUBLISHED GITHUB LINK]  
**Working video:** [ADD VIDEO URL]  
**Deployment / reproducible setup:** `docker compose up --build -d` and the seeding commands in README  

### Deadline and strict blockers

Submission closes **October 18, 2026, 11:59 PM IST**. Official rules require public source, README with graph model and Cypher, working video, setup/deployment, named tracks, and meaningful participant verification. A package alone is **not** a submitted entry.

### Sources

- https://www.wemakedevs.org/hackathons/falkordb
- https://www.wemakedevs.org/hackathons/falkordb/rules
- https://www.wemakedevs.org/blogs/how-to-build-an-agent-that-reasons-over-a-graph
- https://www.falkordb.com/blog/memory-meets-motion-the-falkordb-standouts/
- https://github.com/FalkorDB/falkordb-py

## Mandatory v4 evidence insert (do not simulate this with a prerecorded fake)

After recording the synthetic operator-report event, start a second session and place the **MEMORY CAUSAL TEST** evidence box on screen. Point at the same-topology comparison: **without memory** the surgical pair is preferred, **with memory** credential rotation wins. Explain explicitly that this demonstrates *dependence on prior graph-stored reports*, not proof that the reported outage happened. For a technical judge, execute `python -m maelin.judge --output judge-proof.json` against real FalkorDB and show the CI evidence artifact (see JUDGE_PACKET.md). That command additionally invalidates the old plan after controlled topology drift and cleans up its test graphs.
