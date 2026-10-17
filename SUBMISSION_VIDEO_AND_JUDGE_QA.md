# Maelin hackathon demo script — 3 minutes

This is a recording plan for a REAL running project, not a fictional video transcript. Use the actual browser connected to FalkorDB. Download the Actions artifact \`maelin-real-browser-proof\` as supporting proof if desired.

| Time | Live action | What the judge should see |
| --- | --- | --- |
| 0:00–0:20 | Introduce: “Maelin — see the consequences, remember the cost.” | Animated real graph and connected FalkorDB health |
| 0:20–0:45 | Choose auth-service and Investigate | Verified two multi-hop attacker routes |
| 0:45–1:10 | Open Recon and MCP evidence | Typed MCP calls, Cypher paths and business dependencies |
| 1:10–1:35 | Compare quarantine vs selected surgical pair; Replay | Customer impact comparison; FalkorDB clone routes 2 → 0 |
| 1:35–2:00 | Report synthetic failure and investigate again | Persistent episode/procedure memory changes the plan |
| 2:00–2:20 | Switch to Beta and back | Isolated memory and no cross-tenant reports |
| 2:20–2:40 | Inject synthetic hidden route | New FalkorDB path invalidates old cut; three-route re-investigation |
| 2:40–2:55 | Select vault-sync or import second graph | Dynamic investigation, not a fixed canned scene |
| 2:55–3:00 | Show track names and link to GitHub | Track 01 + Track 02, reproducible source and proof |

When showing LLM behavior, configure a real provider first and expand the specialist \`llm_analysis\` or \`remediation_reasoning\` handoffs. If the system reports deterministic mode, say so and do not call it a live LLM demo.

## Judge Q&A

**What happens when FalkorDB disappears?** Every query, memory operation and simulation fails closed. The frontend is not a pathfinder. The DFS oracle used by unit tests lives under \`tests/\`.

**Are they really agents?** With credentials, separate Recon, Memory and Remediation specialists select restricted graph tools through a bounded LLM loop and persist reasoning/handoff context. Without model credentials, the same safety kernel is intentionally deterministic and labeled as such.

**Is memory just a numerical penalty?** Decision ranking includes a cost-sensitive penalty, but its evidence is retrieved through real episodic, semantic-pattern and procedural FalkorDB subgraphs; live memory ablation shows the causal influence. Similar kinds get discounted evidence weights.

**Can I change the graph?** Yes. Choose any valid source/pivot/target, or import a separate synthetic graph with new interventions into a fresh tenant using the JSON importer.

**Can this change production systems?** No. The only mutations are synthetic topology injection, episode recording and disposable database clone simulation, behind an operator-authenticated boundary.

**What's left after a green CI?** Record and upload a real presentation video; verify the chosen model provider is working; register and submit the project on WeMakeDevs. For a durable public service supply a hosted FalkorDB connection; the bundled web demo is ephemeral.
