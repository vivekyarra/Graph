# Validation status: precisely what was, and was not, tested

As of 2026-10-16, in the local authoring environment:

| Gate | Status | Evidence |
|---|---|---|
| 5,000 seeded randomized optimizer/oracle comparisons | PASS | `tests/test_stress.py` |
| Counterexamples for shorter benign path, incomplete intervention, business disruption, memory-reordered recommendation, drift | PASS | `tests/test_logic.py`, `tests/test_agents.py` |
| Isolated graph-copy replay protocol, partial cut, node outage, drift and cleanup (fake driver) | PASS | `tests/test_simulation.py` |
| Production code has no graph-less fallback | PASS (source invariant) | `tests/test_invariants.py` |
| UI JavaScript parse | PASS | Node.js `vm.Script`; **not** a browser end-to-end test |
| Real FalkorDB queries / Graph.copy / multi-tenant memory / graph DELETE and re-traversal / concurrent handoffs | **PASS in GitHub CI (2026-10-16)** | [First successful run](https://github.com/vivekyarra/Graph/actions/runs/38924960115), 30/30 including both live tests; subsequent expansion pending latest run |
| Real Docker Compose fresh-machine startup | **NOT RUN** | Docker unavailable in this authoring environment |
| GitHub Actions FalkorDB integration | **PASS (2026-10-16)** | [Run 38924960115](https://github.com/vivekyarra/Graph/actions/runs/38924960115); real FalkorDB launched, 30/30 green |
| Public deployment and working video | **NOT DONE** | Participant action required |

**The GitHub run is a real database integration pass.** The authoring container still lacks Docker; clean-machine Docker Compose and the browser demo must be checked separately.

## Clean-machine go/no-go steps

1. `docker compose up --build -d` and inspect `docker compose logs --tail=100 graph app` for errors.
2. `docker compose exec app python -m maelin.seed --tenant alpha`; repeat for beta. Only use `--reset` intentionally, because it destroys that tenant's existing graph state.
3. `python -m pip install -r requirements-dev.txt -r requirements.txt` on your host.
4. `FALKOR_INTEGRATION=1 python -m pytest -q` (PowerShell: `$env:FALKOR_INTEGRATION='1'; python -m pytest -q`). This must PASS, not skip.
5. Open http://localhost:8000; carry out all video steps. Use browser DevTools to ensure no 500/503 errors, verify the sandbox replay creates no leftover `sim_` graph.
6. Inspect FalkorDB Browser and verify stored memory/session edges in both tenants, and that a seeded Beta session has no Alpha memory.
7. The project is already published on the development branch. After these checks, record the demo video and submit to both tracks.

Until the full demo and independent review pass, call this a **real-integration-tested dual-track prototype**, not a proven winning-grade build.
