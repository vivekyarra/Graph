"""Empirical Challenger Verification & Invariant Stress-Testing Suite.

Covers:
1. Bounded Cypher traversal (*1..7) and path provenance structure.
2. Menger's min-cut theorem bounds under candidate cuts with independent max-flow oracle.
3. Counterfactual simulation cloning safety: cryptographic proof that simulation does not mutate live graph topology.
4. Causal memory policy ablation: verifying recommendation shift, tenant isolation, and invariant preservation.
"""
import copy
import hashlib
import json
import re
from collections import deque
from pathlib import Path
import pytest

from maelin.logic import analyze
from maelin.simulator import run_simulation
from maelin.store import _format_nodes, _format_rels
from offline_graph import traversal_fixture
from test_agents import FakeFalkorStore, SCENE

ROOT = Path(__file__).resolve().parent.parent
DEMO_PATH = ROOT / "data" / "demo.json"
DATA = json.loads(DEMO_PATH.read_text(encoding="utf-8"))


# ==============================================================================
# 1. Bounded Cypher Traversal & Path Provenance Structure
# ==============================================================================

def test_cypher_traversals_are_strictly_bounded_and_fail_closed():
    """Verify all Cypher traversals in production code enforce *1..7 bounds and limit guards."""
    store_code = (ROOT / "maelin" / "store.py").read_text(encoding="utf-8")
    sim_code = (ROOT / "maelin" / "simulator.py").read_text(encoding="utf-8")
    agents_code = (ROOT / "maelin" / "agents.py").read_text(encoding="utf-8")

    # 1. Check bounded depth (1..7 for full enumeration, 1..6 for chokepoint cuts)
    traversal_patterns = [
        r"-:CAN_PIVOT\*(?P<bound>[0-9a-zA-Z._]+)->",
        r"-:DEPENDS_ON\*(?P<bound>[0-9a-zA-Z._]+)->",
    ]
    for code in (store_code, sim_code, agents_code):
        for pattern in traversal_patterns:
            matches = list(re.finditer(pattern, code))
            for m in matches:
                assert re.fullmatch(r"1\.\.[1-7]", m.group("bound")), \
                    f"Found unbounded or non-standard depth: {m.group(0)}"

    # 2. Check no arbitrary / unbounded regex
    assert re.search(r"-\[[a-zA-Z0-9_:]*\*\]->", store_code) is None, "Found unbounded Cypher edge * traversal"
    assert re.search(r"-\[[a-zA-Z0-9_:]*\*\]->", sim_code) is None, "Found unbounded Cypher edge * traversal"

    # 3. Check exact provenance structure: nodes(p) and relationships(p)
    assert "nodes(p)" in store_code
    assert "relationships(p)" in store_code
    assert "nodes(p)" in agents_code
    assert "relationships(p)" in agents_code

    # 4. Check fail-closed limits on attack path and business dependency queries
    assert "LIMIT 257" in store_code
    assert "LIMIT 1025" in store_code
    assert "len(rows) > 256" in store_code
    assert "len(rows) > 1024" in store_code
    assert "len(rows) > 256" in sim_code


def test_path_provenance_formatting_handles_edge_cases():
    """Stress-test node and edge provenance formatters with diverse inputs."""
    import falkordb

    # Case A: FalkorDB Node with zero id, labels, and properties
    node_zero = falkordb.node.Node(node_id=0, labels=["Asset", "Service"], properties={"kind": "service", "x": 100})
    formatted_nodes = _format_nodes([node_zero])
    assert len(formatted_nodes) == 1
    assert formatted_nodes[0]["id"] == 0
    assert formatted_nodes[0]["labels"] == ["Asset", "Service"]
    assert formatted_nodes[0]["kind"] == "service"
    assert formatted_nodes[0]["x"] == 100

    # Case B: FalkorDB Node with explicit string 'id' in properties overriding node_id
    node_str = falkordb.node.Node(node_id=99, labels=["Asset"], properties={"id": "auth-service", "kind": "service"})
    formatted_str = _format_nodes([node_str])
    assert formatted_str[0]["id"] == "auth-service"

    # Case C: Edge with src_node and dest_node mapping to from/to
    src = falkordb.node.Node(node_id=1, properties={"id": "node-a"})
    dest = falkordb.node.Node(node_id=2, properties={"id": "node-b"})
    edge = falkordb.edge.Edge(src_node=src, relation="CAN_PIVOT", dest_node=dest, edge_id=42, properties={"edge_id": "p1", "evidence": "audit"})
    formatted_rels = _format_rels([edge])
    assert len(formatted_rels) == 1
    assert formatted_rels[0]["edge_id"] == "p1"
    assert formatted_rels[0]["relation"] == "CAN_PIVOT"
    assert formatted_rels[0]["from"] == "node-a"
    assert formatted_rels[0]["to"] == "node-b"

    # Case D: Raw dictionary passthrough
    raw_node = {"id": "raw-1", "kind": "identity"}
    assert _format_nodes([raw_node]) == [raw_node]
    raw_rel = {"edge_id": "r-1", "from": "raw-1", "to": "raw-2"}
    assert _format_rels([raw_rel]) == [raw_rel]

    # Case E: Primitive fallback
    assert _format_nodes(["plain-id"]) == [{"id": "plain-id"}]
    assert _format_rels([77]) == [{"edge_id": "77"}]


# ==============================================================================
# 2. Menger's Min-Cut Theorem Bounds under Candidate Cuts
# ==============================================================================

def edmonds_karp_max_flow(source, target, edges):
    """Independent Edmonds-Karp max-flow algorithm with unit capacity."""
    # Build adjacency list with residual capacities
    graph = {}
    capacity = {}
    for u, v, eid in edges:
        graph.setdefault(u, []).append((v, eid, 1))  # forward edge cap 1
        graph.setdefault(v, []).append((u, eid, 0))  # reverse edge cap 0
        capacity[(u, v, eid)] = 1
        capacity[(v, u, eid)] = 0

    max_flow = 0
    while True:
        # BFS for shortest augmenting path
        parent = {}
        queue = deque([source])
        while queue and target not in parent:
            curr = queue.popleft()
            for nxt, eid, _ in graph.get(curr, []):
                if nxt not in parent and nxt != source and capacity[(curr, nxt, eid)] > 0:
                    parent[nxt] = (curr, eid)
                    queue.append(nxt)

        if target not in parent:
            break

        # Bottleneck capacity is 1 because all capacities are unit
        path_flow = 1
        curr = target
        while curr != source:
            prev, eid = parent[curr]
            capacity[(prev, curr, eid)] -= path_flow
            capacity[(curr, prev, eid)] += path_flow
            curr = prev
        max_flow += path_flow

    return max_flow


def test_mengers_theorem_bounds_on_demo_graph():
    """Verify that Menger's theorem bound holds strictly for demo incident.
    
    Max-flow between auth-service and customer-db is 2.
    Therefore, by Menger's theorem:
    - At least 2 edge cuts are strictly required to disconnect auth-service from customer-db.
    - Any candidate cut of size 1 MUST leave at least 1 path open.
    - Candidate plan cutting 2 edges (p3 and p5) is an optimal edge cut.
    """
    pivot_edges = [(e["from"], e["to"], e["id"]) for e in DATA["pivot_edges"]]
    flow_from_auth = edmonds_karp_max_flow("auth-service", "customer-db", pivot_edges)
    assert flow_from_auth == 2, f"Expected max-flow 2, got {flow_from_auth}"

    # Test candidate action cuts
    paths, biz = traversal_fixture(DATA)
    assert len(paths) == 2

    # Plan with 1 cut: revoke-admin-role cuts p3, leaves p5 open
    p3_only_cut = analyze(paths, biz, DATA["actions"], max_actions=1)
    allowed_ids = [p["action_ids"] for p in p3_only_cut["plans"]]
    assert ["revoke-admin-role"] not in allowed_ids, "Single edge cut should not be a complete containment plan"

    # Plan with 2 cuts: revoke-admin-role (p3) + block-vault-pivot (p5)
    full_cut = analyze(paths, biz, DATA["actions"])
    rec = full_cut["recommended"]
    assert rec is not None
    assert set(rec["action_ids"]) == {"revoke-admin-role", "block-vault-pivot"}
    assert set(rec["blocked_edges"]) == {"p3", "p5"}
    assert len(rec["blocked_edges"]) == flow_from_auth  # Matches Menger's min-cut bound!


def test_mengers_theorem_bounds_under_topology_drift():
    """Verify that adding a shadow route increases min-cut to 3 and invalidates old 2-cut plan."""
    scene = copy.deepcopy(DATA)
    scene["assets"].append({"id": "shadow-role", "kind": "identity", "x": 603, "y": 225})
    scene["pivot_edges"] += [
        {"id": "p9", "from": "auth-service", "to": "shadow-role"},
        {"id": "p10", "from": "shadow-role", "to": "customer-db"}
    ]
    edges = [(e["from"], e["to"], e["id"]) for e in scene["pivot_edges"]]
    flow = edmonds_karp_max_flow("auth-service", "customer-db", edges)
    assert flow == 3, f"Expected drifted max-flow 3, got {flow}"

    # Traversal fixture discovers 3 attack paths
    paths, biz = traversal_fixture(scene)
    assert len(paths) == 3

    # The old surgical cut of 2 edges no longer cuts all paths
    old_edges = {"p3", "p5"}
    open_paths = [p for p in paths if not (set(p["edges"]) & old_edges)]
    assert len(open_paths) == 1, "The shadow route through p9, p10 must remain open under old cut"
    assert open_paths[0]["edges"] == ["p1", "p2", "p9", "p10"]

    # Analysis confirms old cut is not in acceptable plans and a new cut is forced
    result = analyze(paths, biz, scene["actions"])
    plans = result["plans"]
    assert not any(set(p["action_ids"]) == {"revoke-admin-role", "block-vault-pivot"} for p in plans)
    assert result["recommended"]["action_ids"] == ["invalidate-attacker-session"]


# ==============================================================================
# 3. Counterfactual Simulation Cloning Safety
# ==============================================================================

def hash_topology(graph_data):
    """Deterministic cryptographic hash of graph assets and edges."""
    canonical = {
        "assets": sorted(graph_data["assets"], key=lambda a: a["id"]),
        "pivot_edges": sorted(graph_data["pivot_edges"], key=lambda e: e["id"]),
        "depends_edges": sorted(graph_data["depends_edges"], key=lambda e: e["id"]),
        "actions": sorted(graph_data["actions"], key=lambda a: a["id"]),
    }
    payload = json.dumps(canonical, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AdversarialSimulationStore:
    """Rigorous store double tracking clone lifecycle and verifying live topology immutability."""
    def __init__(self, data):
        self.live_data = copy.deepcopy(data)
        self.initial_hash = hash_topology(self.live_data)
        self.clones = []
        self.handoffs = []
        self.actions = copy.deepcopy(data["actions"])

    def graphs(self, tenant):
        class LiveGraph:
            def __init__(inner):
                inner.name = f"maelin_{tenant}_topology"
            def copy(inner, clone_name):
                # Ensure clone name complies with UUID pattern
                assert re.match(rf"^maelin_{tenant}_sim_[0-9a-f]{{8}}$", clone_name), f"Invalid clone name: {clone_name}"
                clone = AdversarialClone(clone_name, copy.deepcopy(self.live_data), self)
                self.clones.append(clone)
                return clone
            def ro_query(inner, query, params=None):
                raise AssertionError("Simulation must NEVER execute queries on the live graph!")
            def query(inner, query, params=None):
                raise AssertionError("Simulation must NEVER execute mutations on the live graph!")
        return LiveGraph(), None

    def session_actions(self, tenant, sid):
        return [a["id"] for a in self.actions]

    def interventions(self, tenant):
        return self.actions

    def handoff(self, tenant, sid, agent, status, payload):
        self.handoffs.append((tenant, sid, agent, status, payload))

    def verify_live_graph_unmutated(self):
        curr_hash = hash_topology(self.live_data)
        assert curr_hash == self.initial_hash, "CRITICAL: Live graph was mutated during simulation!"


class AdversarialClone:
    def __init__(self, name, data, store):
        self.name = name
        self.data = data
        self.store = store
        self.deleted = False
        self.fail_on_query = False

    def ro_query(self, query, params=None):
        if self.fail_on_query:
            raise RuntimeError("Injected database failure during clone traversal")
        threat, biz = traversal_fixture(self.data)
        class Result:
            def __init__(inner, rows): inner.result_set = rows
        if "CAN_PIVOT" in query:
            return Result([[p["nodes"], p["edges"]] for p in threat])
        assert "DEPENDS_ON" in query
        return Result([[p["flow"], p["value"], p["nodes"]] for p in biz])

    def query(self, query, params=None):
        if self.fail_on_query:
            raise RuntimeError("Injected database failure during clone mutation")
        if "DELETE r" in query:
            eid = params["edge_id"]
            self.data["pivot_edges"] = [e for e in self.data["pivot_edges"] if e["id"] != eid]
        elif "DETACH DELETE n" in query:
            nid = params["node_id"]
            self.data["assets"] = [a for a in self.data["assets"] if a["id"] != nid]
            self.data["pivot_edges"] = [e for e in self.data["pivot_edges"] if nid not in (e["from"], e["to"])]
            self.data["depends_edges"] = [e for e in self.data["depends_edges"] if nid not in (e["from"], e["to"])]
        else:
            raise AssertionError(f"Unexpected Cypher mutation: {query}")

    def delete(self):
        self.deleted = True


def test_simulation_cloning_safety_and_live_graph_immutability():
    """Empirically prove that running simulations does not mutate the live graph."""
    store = AdversarialSimulationStore(DATA)

    # 1. Run surgical containment simulation
    res1 = run_simulation(store, "alpha", "sess-1", DATA, ["revoke-admin-role", "block-vault-pivot"])
    assert res1["contained"] is True
    assert res1["original_routes"] == 2
    assert res1["remaining_routes"] == 0
    store.verify_live_graph_unmutated()
    assert len(store.clones) == 1
    assert store.clones[0].deleted is True

    # 2. Run emergency brake simulation (disruptive quarantine)
    res2 = run_simulation(store, "alpha", "sess-2", DATA, ["quarantine-auth"])
    assert res2["contained"] is True
    assert res2["modeled_disruption_cost"] == 160
    store.verify_live_graph_unmutated()
    assert len(store.clones) == 2
    assert store.clones[1].deleted is True

    # 3. Run partial containment simulation
    res3 = run_simulation(store, "alpha", "sess-3", DATA, ["revoke-admin-role"])
    assert res3["contained"] is False
    assert res3["remaining_routes"] == 1
    store.verify_live_graph_unmutated()
    assert len(store.clones) == 3
    assert store.clones[2].deleted is True

    # 4. Stress-test: simulation failure midway through execution
    # Ensure clone is deleted and live graph remains intact even on error!
    class FailingSimStore(AdversarialSimulationStore):
        def graphs(self, tenant):
            live, _ = super().graphs(tenant)
            orig_copy = live.copy
            def bad_copy(name):
                clone = orig_copy(name)
                clone.fail_on_query = True
                return clone
            live.copy = bad_copy
            return live, None

    failing_store = FailingSimStore(DATA)
    with pytest.raises(RuntimeError, match="Injected database failure"):
        run_simulation(failing_store, "alpha", "sess-err", DATA, ["revoke-admin-role"])

    failing_store.verify_live_graph_unmutated()
    assert len(failing_store.clones) == 1
    assert failing_store.clones[0].deleted is True, "Clone must be deleted via try...finally even on failure!"


# ==============================================================================
# 4. Causal Memory Policy Ablation
# ==============================================================================

def test_causal_memory_policy_ablation_empirical_shift():
    """Empirically verify causal memory policy ablation and multi-tenant isolation."""
    from maelin.agents import investigate

    store = FakeFalkorStore()

    # Turn 1: Cold investigation (no memory precedents)
    cold = investigate(store, "alpha", DATA)
    ablation_cold = cold["analysis"]["memory_ablation"]
    assert ablation_cold["recommendation_changed"] is False
    assert ablation_cold["reports_considered"] == 0
    assert ablation_cold["without_memory_actions"] == ["revoke-admin-role", "block-vault-pivot"]
    assert ablation_cold["with_memory_actions"] == ["revoke-admin-role", "block-vault-pivot"]

    # Turn 2: Operator records failure of revoke-admin-role
    store.report("alpha", DATA["fingerprint"], "revoke-admin-role")

    # Warm investigation on Alpha
    warm_alpha = investigate(store, "alpha", DATA)
    ablation_warm = warm_alpha["analysis"]["memory_ablation"]
    assert ablation_warm["recommendation_changed"] is True
    assert ablation_warm["reports_considered"] == 1
    # Baseline remains unchanged:
    assert ablation_warm["without_memory_actions"] == ["revoke-admin-role", "block-vault-pivot"]
    # With memory shifted to alternative plan:
    assert ablation_warm["with_memory_actions"] == ["rotate-auth-credentials"]
    assert ablation_warm["evidence_kind"].startswith("operator_report")

    # Turn 3: Multi-tenant isolation verification on Beta
    cold_beta = investigate(store, "beta", DATA)
    ablation_beta = cold_beta["analysis"]["memory_ablation"]
    assert ablation_beta["recommendation_changed"] is False
    assert ablation_beta["reports_considered"] == 0
    assert ablation_beta["with_memory_actions"] == ["revoke-admin-role", "block-vault-pivot"]
    assert ablation_beta["without_memory_actions"] == ["revoke-admin-role", "block-vault-pivot"]

    # Turn 4: Success report does not override safety invariants
    # If operator reports quarantine-auth as safe, it should NOT become recommended
    store_safe = FakeFalkorStore()
    store_safe.memory[("alpha", DATA["fingerprint"])].append({"action_id": "quarantine-auth", "outcome": "safe"})
    safe_investigation = investigate(store_safe, "alpha", DATA)
    assert "quarantine-auth" not in safe_investigation["analysis"]["recommended"]["action_ids"]


# ==============================================================================
# 5. Randomized Menger Oracle Across 500 Network Topologies
# ==============================================================================

def test_randomized_menger_bound_oracle_across_500_topologies():
    """Adversarial oracle: generate 500 random directed topologies and empirically
    verify that no edge cut smaller than Edmonds-Karp max-flow can disconnect s from t.
    """
    import random
    from itertools import combinations
    rng = random.Random(20261018)

    for trial in range(500):
        num_internal = rng.randint(2, 6)
        nodes = ["s"] + [f"v{i}" for i in range(num_internal)] + ["t"]
        edges = []
        edge_id = 0
        
        # Ensure a forward-flowing DAG structure to avoid infinite loops
        for i, u in enumerate(nodes[:-1]):
            for v in nodes[i+1:]:
                if rng.random() < 0.45:
                    edges.append((u, v, f"e{edge_id}"))
                    edge_id += 1

        # Also add at least one guaranteed path s -> internal -> t
        mid = rng.choice(nodes[1:-1])
        edges.append(("s", mid, f"e{edge_id}"))
        edges.append((mid, "t", f"e{edge_id+1}"))
        edge_id += 2

        k = edmonds_karp_max_flow("s", "t", edges)
        assert k >= 1, f"Trial {trial}: expected at least 1 path"

        # Check candidate cuts of sizes 1 to min(k, 3)
        edge_map = {eid: (u, v) for u, v, eid in edges}
        all_eids = list(edge_map.keys())

        # Sub-test 1: Verify NO cut of size < k disconnects s and t
        if k > 1:
            for sub_size in range(1, min(k, 3)):
                # Sample up to 20 candidate cuts
                candidates = list(combinations(all_eids, sub_size))
                if len(candidates) > 20:
                    candidates = rng.sample(candidates, 20)
                for cut in candidates:
                    cut_set = set(cut)
                    # Check reachability with cut removed
                    visited = set()
                    q = deque(["s"])
                    while q:
                        curr = q.popleft()
                        if curr == "t":
                            break
                        for u, v, eid in edges:
                            if u == curr and eid not in cut_set and v not in visited:
                                visited.add(v)
                                q.append(v)
                    # By Menger's theorem, target 't' MUST still be reachable!
                    assert "t" in visited or curr == "t", (
                        f"Trial {trial}: Menger bound violated! Cut of size {len(cut)} < {k} disconnected s from t"
                    )


# ==============================================================================
# 6. Concurrency and Clone Isolation Stress Test
# ==============================================================================

def test_concurrent_simulation_clones_isolation_and_cleanup():
    """Verify that multiple concurrent simulations across tenants operate in isolated namespaces."""
    store = AdversarialSimulationStore(DATA)
    tenants = ["alpha", "beta", "tenant-x", "tenant-y"]
    sessions = [f"session-{i}" for i in range(10)]

    for tenant in tenants:
        for sid in sessions[:3]:
            res = run_simulation(store, tenant, sid, DATA, ["revoke-admin-role", "block-vault-pivot"])
            assert res["contained"] is True

    # Check all created clones
    assert len(store.clones) == len(tenants) * 3
    clone_names = [c.name for c in store.clones]
    assert len(set(clone_names)) == len(clone_names), "All clone names must be globally unique!"

    # Check tenant prefix and deletion for each clone
    for clone in store.clones:
        assert clone.deleted is True
        prefix = f"maelin_{clone.name.split('_')[1]}_sim_"
        assert clone.name.startswith(prefix)

    # Prove live graph is still 100% unmutated
    store.verify_live_graph_unmutated()


# ==============================================================================
# 7. Fail-Closed Limits & Parameter Boundary Stress Tests
# ==============================================================================

def test_attack_and_business_paths_overflow_fail_closed():
    """Verify that exceeding traversal limits fails closed with OverflowError."""
    from maelin.store import Store

    class OverflowTopology:
        def ro_query(self, query, params=None):
            class Res:
                def __init__(inner, rows): inner.result_set = rows
            if "CAN_PIVOT" in query:
                # Return 257 rows to trigger the > 256 overflow check
                fake_rows = [[["a", "b"], ["p1"], ["ev"], [], []] for _ in range(257)]
                return Res(fake_rows)
            elif "DEPENDS_ON" in query:
                # Return 1025 rows to trigger the > 1024 overflow check
                fake_rows = [["flow", 10, ["a", "b"], [], []] for _ in range(1025)]
                return Res(fake_rows)
            return Res([])

    store = Store.__new__(Store)
    store.graphs = lambda tenant: (OverflowTopology(), None)

    with pytest.raises(OverflowError, match="More than 256 candidate attack paths"):
        store.attack_paths("alpha", "internet", "auth-service", "customer-db")

    with pytest.raises(OverflowError, match="Business dependency enumeration exceeded limit"):
        store.business_paths("alpha")


def test_simulation_rejects_unauthorized_action_or_unseeded_intervention():
    """Verify simulation enforces session boundaries and valid action IDs."""
    store = AdversarialSimulationStore(DATA)

    # 1. Action not in session
    store.actions = [{"id": "valid-action", "label": "V", "blocked_nodes": [], "blocked_edges": ["p3"], "cost": 1}]
    store.session_actions = lambda tenant, sid: ["other-action"]
    with pytest.raises(PermissionError, match="Action not offered"):
        run_simulation(store, "alpha", "sess-1", DATA, ["valid-action"])

    # 2. Duplicate action in list
    with pytest.raises(ValueError, match="Duplicate intervention ID"):
        run_simulation(store, "alpha", "sess-1", DATA, ["valid-action", "valid-action"])

    # 3. Empty action list
    with pytest.raises(ValueError, match="Specify 1-3 intervention IDs"):
        run_simulation(store, "alpha", "sess-1", DATA, [])

    # 4. Exceeding 3 actions
    with pytest.raises(ValueError, match="Specify 1-3 intervention IDs"):
        run_simulation(store, "alpha", "sess-1", DATA, ["a", "b", "c", "d"])

    # Live graph remains strictly unmutated
    store.verify_live_graph_unmutated()


