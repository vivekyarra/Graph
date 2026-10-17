# Maelin validation matrix — October 17, 2026

The GitHub Actions run is the source of truth, not this static text. See https://github.com/vivekyarra/Graph/actions.

| Validation gate | Automated proof |
| --- | --- |
| Required graph engine | Real FalkorDB driver and Graph.copy are exercised |
| Multi-hop discovery | Cypher bounded attack path and dependency queries; no production Python DFS |
| Optimizer correctness | 5,000 randomized cases checked against a separately written exhaustive oracle |
| Replay | Actual graph copy, DELETE and re-query; incomplete cuts are rejected |
| Context | Per-tenant graph-backed episode, semantic-pattern, procedure and conversation records |
| Isolation | Alpha/Beta separation, invalid action rejection, concurrent sessions |
| MCP | Actual stdio client to typed tools, persisted tool-call ledger |
| Dynamic uploads | Validator tests + live second-topology selection + browser API journey |
| Real browser | Headless Chromium clicks investigation, replay, memory failure, drift and scenario import |
| Model tool discipline | Fake-model unit tests restrict requested tool names and host-owned arguments |
| Standalone demo | Dedicated Dockerfile.demo smoke workflow; check job conclusion in Actions |

**Honest boundaries:** CI model tests use fake model responses for reproducibility; an actual hosted LLM or Ollama instance needs credentials and must be smoke-tested in a real runtime. Impact values are declared synthetic prioritization units, not measured currency losses. The standalone public container uses real FalkorDB but is ephemeral across restarts; persistent online memory requires external hosted FalkorDB or a Docker volume. No real cloud remediations occur.

Use the Actions artifacts and video captures as engineering evidence, then produce a working demonstration video for the hackathon submission.
