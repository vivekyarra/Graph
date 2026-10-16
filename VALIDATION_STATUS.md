# Validation status: precisely what was, and was not, tested

As of 2026-10-16, in the local authoring environment:

| Gate | Status | Evidence |
|---|---|---|
| 600 seeded randomized optimizer/oracle comparisons | PASS | `tests/test_stress.py` |
| Counterexamples for shorter benign path, incomplete intervention, business disruption, memory-reordered recommendation, drift | PASS | `tests/test_logic.py`, `tests/test_agents.py` |
| Isolated graph-copy replay protocol, partial cut, node outage, drift and cleanup (fake driver) | PASS | `tests/test_simulation.py` |
| Production code has no graph-less fallback | PASS (source invariant) | `tests/test_invariants.py` |
| UI JavaScript parse | PASS | Node.js `vm.Script`; **not** a browser end-to-end test |
| Real FalkorDB queries / Graph.copy / multi-tenant memory / graph DELETE and re-traversal / concurrent handoffs | **NOT RUN** | `tests/test_live_falkordb.py` requires `FALKOR_INTEGRATION=1` + a real FalkorDB service |
| Real Docker Compose fresh-machine startup | **NOT RUN** | Docker unavailable in this authoring environment |
| GitHub Actions FalkorDB integration | **NOT RUN** | `.github/workflows/falkordb-integration.yml` exists but has not executed in GitHub |
| Public deployment and working video | **NOT DONE** | Participant action required |

**Do not interpret offline driver mocks or schema-level Cypher inspection as a live DB pass.**

## Clean-machine go/no-go steps

1. `docker compose up --build -d` and inspect `docker compose logs --tail=100 graph app` for errors.
2. `docker compose exec app python -m maelin.seed --tenant alpha`; repeat for beta. Only use `--reset` intentionally, because it destroys that tenant's existing graph state.
3. `python -m pip install -r requirements-dev.txt -r requirements.txt` on your host.
4. `FALKOR_INTEGRATION=1 python -m pytest -q` (PowerShell: `$env:FALKOR_INTEGRATION='1'; python -m pytest -q`). This must PASS, not skip.
5. Open http://localhost:8000; carry out all video steps. Use browser DevTools to ensure no 500/503 errors, verify the sandbox replay creates no leftover `sim_` graph.
6. Inspect FalkorDB Browser and verify stored memory/session edges in both tenants, and that a seeded Beta session has no Alpha memory.
7. Only after these checks, publish the repository, record the demo video, and submit to both tracks.

Until steps 1–6 pass on real infrastructure, call this an **engineered dual-track prototype**, not a proven winning-grade build.
