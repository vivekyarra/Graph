"""Tests for the Track 01/02 proof surface: chokepoint cut math, evidence IDs,
protocol-level read-only queries, FalkorDB telemetry and proven playbooks.

These run offline against strict fakes; live equivalents live in
tests/test_live_graph_intel.py and are gated on FALKOR_INTEGRATION=1.
"""
import types
from pathlib import Path

import pytest

from maelin.store import Store
from maelin.evidence import (assign_evidence_ids, severance_sentence,
                             traversed_node_ids, verify_agent_remediation)
from maelin.telemetry import telemetry_scope

ROOT = Path(__file__).resolve().parent.parent


class Result:
    def __init__(self, rows=None, run_time_ms=1.18):
        self.result_set = rows or []
        self.run_time_ms = run_time_ms


class ReadOnlySpy:
    """Fails the test if any code path reaches for a write query."""

    def __init__(self, handler):
        self.handler = handler
        self.ro_calls = []

    def ro_query(self, cypher, params=None):
        self.ro_calls.append((cypher, params))
        return self.handler(cypher, params)

    def query(self, cypher, params=None):
        raise AssertionError(f"read-only tool issued GRAPH.QUERY: {cypher}")


def test_critical_chokepoints_combines_betweenness_and_cut_simulation():
    def handler(cypher, params):
        if "algo.betweenness" in cypher:
            return Result([["edge-gateway", "service", 0.66],
                           ["auth-service", "service", 0.33]])
        if "chokepoint_service" in cypher:
            return Result([
                ["edge-gateway", 2, 2, 100.0, ["admin-role"]],
                ["auth-service", 1, 2, 50.0, ["admin-role"]],
            ])
        raise AssertionError(f"unexpected query: {cypher}")

    spy = ReadOnlySpy(handler)
    store = Store.__new__(Store)
    store.graphs = lambda tenant: (spy, None)

    result = store.critical_chokepoints("alpha", vulnerable="auth-service",
                                        source="internet", target="customer-db")
    assert result["betweenness"][0]["service"] == "edge-gateway"
    top = result["chokepoints"][0]
    assert top["chokepoint_service"] == "edge-gateway"
    assert top["paths_severed"] == 2 and top["total_paths"] == 2
    assert top["pct_blast_radius_eliminated"] == 100.0
    assert top["target_roles"] == ["admin-role"]
    assert top["betweenness"] == 0.66
    # Pure GRAPH.RO_QUERY: the spy raises on any write.
    assert all(p is not None for _, p in spy.ro_calls)


def test_betweenness_failure_degrades_gracefully():
    def handler(cypher, params):
        if "algo.betweenness" in cypher:
            raise RuntimeError("betweenness is not supported on a graph this small")
        return Result([["auth-service", 1, 1, 100.0, ["admin-role"]]])

    store = Store.__new__(Store)
    store.graphs = lambda tenant: (ReadOnlySpy(handler), None)
    result = store.critical_chokepoints("alpha", vulnerable="auth-service",
                                        source="internet", target="customer-db")
    assert result["betweenness"] == []
    assert result["betweenness_available"] is False
    assert result["chokepoints"][0]["chokepoint_service"] == "auth-service"


def test_severance_sentence_states_exact_fraction():
    sentence = severance_sentence([{"service": "auth-service", "paths_severed": 2,
                                    "total_paths": 3, "target_roles": ["admin-role"]}])
    assert sentence == ("Isolating `auth-service` severs 2 of 3 (66.7%) "
                        "active exploit paths to `admin-role`.")


def test_evidence_ids_are_deterministic_and_hallucination_is_caught():
    paths = [{"nodes": ["internet", "edge-gateway", "auth-service", "admin-role"],
              "edges": ["p1", "p2", "p3"]}]
    tagged = assign_evidence_ids(paths)
    assert tagged[0]["evidence_id"] == "[E1]"
    traversed = traversed_node_ids(tagged)
    assert traversed == ["internet", "edge-gateway", "auth-service", "admin-role"]

    plan = {"blocked_nodes": ["auth-service"], "blocked_edges": []}
    ok = verify_agent_remediation({"recommended": plan}, traversed)
    assert ok["verified"] is True
    assert ok["verified_nodes"] == ["auth-service"]
    assert ok["unverified_nodes"] == []

    bad = verify_agent_remediation(
        {"recommended": {"blocked_nodes": ["ghost-service"], "blocked_edges": []}}, traversed)
    assert bad["verified"] is False
    assert bad["unverified_nodes"] == ["ghost-service"]


def test_edge_cut_citations_resolve_to_traversed_endpoints():
    paths = [{"nodes": ["internet", "edge-gateway", "auth-service", "admin-role"],
              "edges": ["p1", "p2", "p3"]}]
    check = verify_agent_remediation(
        {"recommended": {"blocked_nodes": [], "blocked_edges": ["p3"]}},
        traversed_node_ids(paths), paths)
    assert check["verified"] is True
    assert check["verified_nodes"] == ["admin-role", "auth-service"]


def test_telemetry_records_graph_agent_query_type_and_runtime():
    def handler(cypher, params):
        return Result([[["internet", "auth-service", "customer-db"],
                        ["p2"], [], [], []]], run_time_ms=1.183456)

    spy = ReadOnlySpy(handler)
    store = Store.__new__(Store)
    store.graphs = lambda tenant: (spy, None)
    with telemetry_scope() as trace:
        store.attack_paths("alpha", "internet", "auth-service", "customer-db")
    assert len(trace) == 1
    row = trace[0]
    assert row["query_type"] == "ro_query"
    assert row["agent_name"] == "Recon & Graph Mapper"
    assert row["run_time_ms"] == 1.183
    assert row["evidence_id"] == "[E1]"
    assert "$source" in row["cypher"] and "internet" not in row["cypher"]


def test_recall_proven_playbook_ranks_by_usage_and_mttr():
    queries = []

    def handler(cypher, params):
        queries.append((cypher, params))
        return Result([["revoke-admin-role", "maelin:playbook:revoke-admin-role",
                        3, 42.5, "2026-10-18T10:00:00+00:00"]])

    store = Store.__new__(Store)
    store.graphs = lambda tenant: (None, ReadOnlySpy(handler))
    rows = store.recall_proven_playbook("alpha", "exploited-identity-to-customer-db", "service")
    assert rows == [{"playbook_id": "revoke-admin-role",
                     "remediation_cmd": "maelin:playbook:revoke-admin-role",
                     "times_used": 3, "avg_mttr_seconds": 42.5,
                     "last_used_at": "2026-10-18T10:00:00+00:00"}]
    cypher, params = queries[0]
    assert params == {"cve_id": "exploited-identity-to-customer-db",
                      "service_tier": "service", "limit": 3}
    assert "RESOLVED_BY" in cypher and "Playbook" in cypher


def test_recon_handoff_carries_chokepoints_and_tier():
    from maelin.agents import ReconAgent
    scene = {"source": "internet", "vulnerable": "auth-service",
             "target": "customer-db", "fingerprint": "fp"}

    class Store:
        def attack_paths(self, *a):
            return [{"nodes": ["internet", "auth-service"], "edges": ["p2"]}]

        def business_paths(self, *a):
            return []

        def chokepoints(self, *a):
            return []

        def critical_chokepoints(self, *a):
            return {"chokepoints": [{"service": "auth-service", "paths_severed": 1,
                                     "total_paths": 1, "pct_blast_radius_eliminated": 100.0,
                                     "target_roles": ["admin-role"]}],
                    "betweenness": [], "betweenness_available": False}

        def topology(self, *a):
            return {"nodes": [{"id": "auth-service", "kind": "service"}], "edges": []}

        def interventions(self, *a):
            return [{"id": "revoke-admin-role", "blocked_edges": ["p2"],
                     "blocked_nodes": []}]

        def handoff(self, tenant, sid, agent, status, payload):
            self.payload = payload

    store = Store()
    ReconAgent().run(store, "alpha", "sid", scene)
    assert store.payload["service_tier"] == "service"
    assert store.payload["critical_chokepoints"][0]["paths_severed"] == 1
    assert store.payload["interventions"][0]["id"] == "revoke-admin-role"


def test_mcp_server_exposes_new_proof_tools():
    src = (ROOT / "maelin" / "mcp_server.py").read_text(encoding="utf-8")
    for name in ("find_critical_chokepoints", "recall_proven_playbook",
                 "find_attack_chokepoints"):
        assert f"def {name}(" in src
    # No tool may accept free-form Cypher.
    assert "execute_cypher" not in src


def test_api_exposes_chokepoint_and_playbook_routes():
    src = (ROOT / "maelin" / "api.py").read_text(encoding="utf-8")
    assert '@api.get("/api/chokepoints")' in src
    assert '@api.get("/api/playbooks")' in src
