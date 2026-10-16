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

## Verified on real FalkorDB + real browser (final UI revision)

- Commit `6cd0d9032511f0ec941fa2ed1f1df77340c73e3f` passed GitHub Actions run https://github.com/vivekyarra/Graph/actions/runs/38930127090 .
- **42 passed, 1 non-failing third-party warning** from `FALKOR_INTEGRATION=1 python -m pytest -q` against an actual FalkorDB container. This includes live Cypher, concurrent handoffs, disposable graph replay/cleanup, memory isolation, and synthetic topology drift.
- `python -m maelin.judge --output judge-proof.json` passed, producing `maelin-dual-track-evidence` (artifact ID `12058945413`).
- Chromium launched the actual Dockerized FastAPI application with no API response mocks, passed the complete UI sequence, and saved screenshots plus a real-browser walkthrough in artifact `maelin-real-browser-proof` (artifact ID `12058144105`).
- These tests validate the **synthetic application scenario** and the integration claims, not real-cloud exploitability, forensic certainty, or production readiness.


## Submission gates not yet fulfilled

- Participant-led clean-machine UI+Docker smoke test and code review.
- Public or unlisted real app demo video, actual recorded behavior (not mocked screenshot).
- Verify registration, team information, consent to AI coding assistance disclosure, and submission on organizer's site by Oct 18 2026 23:59 IST.

No official scoring rubric or winning likelihood is asserted. User-visible simulations are synthetic and cannot certify real-world security.

## Live CI progression

- Commit `430deb4`: full real FalkorDB tests and self-cleaning judge harness both passed, with `maelin-dual-track-evidence` artifact.
- Commit `2a894b8`: FalkorDB/agent tests and the judge harness passed, then a browser test assertion failed because it looked for an internal action ID where the UI intentionally displays a human-readable label. Browser regression assertion corrected in the next revision; subsequent full real-browser runs passed.

- Commit `a5bce17`: full GitHub Actions **42 passed, 1 warning** against real FalkorDB, plus self-cleaning judge harness and full Chrome browser E2E (cold graph, real graph clone replay, memory change, injected shadow route). Two artifacts uploaded: `maelin-dual-track-evidence` and `maelin-real-browser-proof`. Verified run: https://github.com/vivekyarra/Graph/actions/runs/38929417346 .
- Final UI refinement commit `6cd0d903`: full real FalkorDB tests, judge proof, and real browser all passed in CI run 38930127090. The rendered agent handoff area now contains a readable Recon → Memory → Remediation timeline and expandable raw graph evidence.