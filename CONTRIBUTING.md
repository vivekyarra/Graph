# Contributing to MAELIN

Thank you for your interest in contributing to MAELIN. As an open-source research and engineering platform for graph-native incident reasoning on FalkorDB, we hold high standards for code clarity, safety invariants, and reproducible evidence.

---

## Architecture Principles & Invariants

When contributing code, please ensure adherence to our core architectural invariants:

1. **Graph-Native Source of Truth**: FalkorDB is the primary and sole runtime engine. Production modules must never include in-memory graph fallbacks (e.g. SQLite, NetworkX, in-memory adjacency lists). If FalkorDB is unreachable, the system must fail closed (`HTTP 503 Service Unavailable`).
2. **Zero-Side-Effect Counterfactual Simulation**: Never run destructive simulations on live production or operational graphs. All counterfactual action replay must execute on disposable graph clones created via `Graph.copy()`, using unique session keys (`maelin_{tenant}_sim_{uuid}`) and clean up in strict `try...finally` blocks.
3. **Multi-Tenant Segregation**: All queries must enforce tenant namespacing (`maelin_{tenant}_*`). Never write cross-tenant queries.
4. **Zero-In-Memory Agent State**: Multi-agent handoffs must be persisted as immutable graph transactions (`(:Session)-[:HAS_HANDOFF]->(:Handoff)`), never passed via Python globals or mutable shared in-memory dictionaries.

---

## Local Development Setup

### Prerequisites
* Python 3.11+
* Docker & Docker Compose (for local FalkorDB runtime)
* Git

### Step-by-Step Environment Setup

```bash
# 1. Clone repository
git clone https://github.com/vivekyarra/Graph.git
cd Graph

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .\.venv\Scripts\activate

# 3. Install development dependencies
pip install -r requirements-dev.txt -r requirements.txt

# 4. Start local FalkorDB instance
docker compose up -d graph

# 5. Seed synthetic development tenants
python -m maelin.seed --tenant alpha
python -m maelin.seed --tenant beta

# 6. Start local development server
uvicorn maelin.api:api --reload --port 8000
```

---

## Running Verification & Tests

Every pull request must pass the comprehensive test suite:

```bash
# Run offline invariant and logic tests
pytest -q

# Run live FalkorDB integration suite
FALKOR_INTEGRATION=1 pytest -q

# Run empirical verification harness
python -m maelin.verify --output verification-proof.json
```

---

## Pull Request Workflow

1. Create a feature branch: `git checkout -b feat/your-feature-name`
2. Implement your changes following PEP 8 conventions and existing type hints.
3. Ensure all existing tests pass (`88+ passed, 0 failures`).
4. Commit with semantic commit messages: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`.
5. Open a pull request against `main`.
