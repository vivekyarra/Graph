# Maelin v4 validation register — 16 October 2026

The current code is intended for an official Graph Hacks **dual-track** entry:
- Track 01: Agents That Act on Connected Data
- Track 02: Agent Memory and Coordination

## Verified in local authoring environment

- Python unit suite: **39 passed, 3 skipped** (3 real-FalkorDB cases gated on `FALKOR_INTEGRATION=1`).
- Existing randomized optimizer/oracle suite: **5,000 cases** passed; explicit catalog cap at 48 interventions and maximum of 3 interventions per plan.
- `python -m compileall` and `node --check` on the dashboard's JavaScript passed.
- Graph authorization: remote-mode read graph and session trace APIs now require operator token; graph-mutating endpoints fail closed without token/local mode.
- New controlled memory ablation: compares same topology and interventions with and without recalled reports and stores the comparison with the durable remediator handoff.
- Deterministic goal selection: the 'prefer fewer changes' UI priority is now respected even without an optional LLM, but only inside a narrow bounded cost and impact envelope.
- New graph provenance fields: attack-path edges include synthetic evidence annotations.

## Gated for live CI on this revision

- Real FalkorDB live end-to-end Cypher traversals, simultaneous session handoffs, replay and cleanup, memory isolation, and drift.
- New one-command judge harness: `python -m maelin.judge --output judge-proof.json`, which creates ephemeral synthetic tenant graphs and checks all track claims while deleting them.
- CI evidence artifact `maelin-dual-track-evidence`, generated only after successful live run.

Earlier v3 commits have had successful real FalkorDB CI runs. **This does not certify the current v4 change until its own job passes.**

## Submission gates not yet fulfilled

- Participant-led clean-machine UI+Docker smoke test and code review.
- Public or unlisted real app demo video, actual recorded behavior (not mocked screenshot).
- Verify registration, team information, consent to AI coding assistance disclosure, and submission on organizer's site by Oct 18 2026 23:59 IST.

No official scoring rubric or winning likelihood is asserted. User-visible simulations are synthetic and cannot certify real-world security.

## Live CI progression

- Commit `430deb4`: full real FalkorDB tests and self-cleaning judge harness both passed, with `maelin-dual-track-evidence` artifact.
- Commit `2a894b8`: FalkorDB/agent tests and the judge harness passed, then a browser test assertion failed because it looked for an internal action ID where the UI intentionally displays a human-readable label. Browser regression test corrected in the next revision. Real browser journey remains a required passing gate before release to `main`.
