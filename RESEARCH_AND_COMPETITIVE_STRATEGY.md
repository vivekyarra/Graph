# Why Maelin and not a prettier SentryGraph?

**Scope:** Evidence-oriented review of a sample of real published winners / standouts from comparable AI-agent, graph and WeMakeDevs hackathons; not an exhaustive census of all hackathons. Conclusions on what judges *will* select are hypotheses, not guarantees.

## Official Graph Hacks alignment

The organizer's pages explicitly list track 01 (multi-hop reasoning; graph algorithms; MCP-based tools; actions based on graph; explainability) and track 02 (episodic, semantic and procedural memory; persistent history; handoffs; concurrency; tenant isolation). Official rules require central, indispensable FalkorDB use; public code; schema and Cypher; README; demo; working setup; permitted data; AI-assistance disclosure. One entry can target multiple tracks. The event deadline is Oct 18, 2026 at 11:59 PM IST. No public numeric scoring rubric was found on the event pages.

Original SentryGraph overlaps the organizer's own Oct 15 "Blast Radius" tutorial: an on-call agent that traces service dependencies and retrieves previous findings. That overlap creates a differentiation problem even if the architecture is functional.

## Evidence from recognized projects

1. **Atrium (FalkorDB Memory Meets Motion, 1st overall).** FalkorDB's sponsor recap describes how learning *misconceptions* become first-class graph nodes, changing how remediation is selected. Lesson: model a discriminative reasoning object, not just a graph of facts. https://www.falkordb.com/blog/memory-meets-motion-the-falkordb-standouts/
2. **AgentCourt Precedent (same event, showcase standout).** Separate deliberation roles plus a deterministic gate and past rulings show why a graph-backed past outcome changes a future consequential action. Lesson: actual enforceable guardrails beat an LLM claiming caution. Same source as above.
3. **Hopper (same event, security-triage standout).** A chain from advisory to package to customer contract answers a specific, financially consequential question. Lesson: business consequences and inspectable paths are stronger than “CVE detected.” Same source as above.
4. **RiskWise (Microsoft AI Agents Hackathon 2025, Best Overall).** A full-stack supply chain risk workflow with usable interface and end-to-end business framing. Lesson: usefulness and completeness. https://microsoft.github.io/AI_Agents_Hackathon/winners/
5. **Memoria Scholae (AI Agents Memories That Last, Grand Prize + sponsor awards, as reported by the project's Devpost page).** Visible Cypher evidence, reproducible workflows, measured latency, and polished UX. Lesson: let the judge inspect the tool, the graph path and the result. https://devpost.com/software/memoria-scholae-research-that-remembers
6. **DebugProof (WeMakeDevs Agents of SigNoz, Track 02 Grand Winner).** Its distinctive move was injecting the *same failure* into two builds, then using real SigNoz evidence to make a release decision. Lesson: measured negative controls and real substrate execution—not a static demo. https://archive.wemakedevs.org/hackathons/signoz/projects/all
7. **RootCause (same WeMakeDevs event, Track 03 Grand Winner).** Distinctive environment (hydroponic farm) plus live controlled fault injection and comprehensive sponsor product use. Lesson: judges notice demos where a button changes the world and the underlying technology visibly reacts. Same source as above.
8. **GitLab AI Hackathon (LORE Grand Prize).** Official winner announcement credits routing across specialized agents, knowledge-graph loop prevention and dashboard. Lesson: sophisticated coordination must be accompanied by inspectable system behavior. https://gitlab.devpost.com/updates/41783-meet-the-winners

## What to copy as *principles*, not code

- Single understandable problem with an immediate consequence.
- An unmistakable before/after intervention, not just a conversational answer.
- Graph queries and persistence that demonstrably alter the outcome.
- An explicit correct refusal when data are missing or a plan is incomplete.
- A falsifiable ablation: stop FalkorDB, remove memory, remove one attack path, or inject a prior failed action.
- High quality frontend with explanation that a non-security judge grasps immediately.

## Why Maelin is different from the earlier blueprint

The original SentryGraph: “find attack path; hand off state; use a playbook.” Maelin adds counterfactual graph-cut planning, paired business-dependency traversals, adversarial shorter-benign-route coverage, an auditable persistent handoff contract, synthetic fault injection that adds a third route and forces a new action, operator-reported negative memory that demonstrably changes a second session's optimal action, and synthetic impact measured for two futures.

## What must still be built/tested to justify claiming winner-grade

1. Live FalkorDB Cypher and Docker compatibility verified by `tests/test_live_falkordb.py`, with screenshot/log artifacts.
2. A working public deployment, or genuinely flawless documented clean-machine setup.
3. Stronger memory transfer: failure mechanisms, aging, reliability controls, and tenant-authenticated writes. Current exact-fingerprint memory is useful but basic.
4. More real-world credibility: evidence for IAM transitions and actual read-only infrastructure ingestion, without restricted data.
5. Real counterfactual validation: simulate an intervention and measure observed disruption in a local lab, not just an operator click.
6. Concurrent writing stress tests and a real LLM tool-choice demonstration if you want to argue full multi-agent autonomy.

**Engineering assessment:** this prototype now offers a credible differentiated competition direction, but has *not* crossed the evidentiary bar for a verified winning-grade submission. Report it as a strong prototype until items 1–2 are completed, not a confirmed winner.
