"""Unit tests for the 6 critical hackathon upgrades.

Covers:
1. algo.pageRank centrality in store.py & mcp_server.py
2. simulator.py clone name format & cleanup
3. store.py exact path provenance (nodes(p), relationships(p))
4. README.md AI disclosure & core Cypher queries
5. 1-click Reset Demo State API (/api/demo/reset) & Cockpit UI wiring
6. Track 03 Company Brain team ownership subgraph in seed, store, mcp, and api
"""
import copy
import json
import os
import re
import types
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
SCENE = json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8"))


def test_asset_centrality_calculation_with_mock_graph():
    from maelin.store import Store

    class MockQueryResult:
        def __init__(self, rows):
            self.result_set = rows

    class MockTopology:
        def query(self, q, params=None):
            assert "algo.pageRank" in q
            return MockQueryResult([
                ["auth-service", "authentication", 0.4521],
                ["customer-db", "primary_datastore", 0.3812],
                ["edge-gateway", "api_gateway", 0.1245],
            ])

    store = Store.__new__(Store)
    store.graphs = lambda tenant: (MockTopology(), None)

    results = store.compute_asset_centrality("alpha")
    assert len(results) == 3
    assert results[0] == {"asset_id": "auth-service", "role": "authentication", "centrality_score": 0.4521}
    assert results[1]["centrality_score"] == 0.3812
    assert results[2]["asset_id"] == "edge-gateway"


def test_team_ownership_query_with_mock_graph():
    from maelin.store import Store

    class MockQueryResult:
        def __init__(self, rows):
            self.result_set = rows

    class MockTopology:
        def ro_query(self, q, params=None):
            assert "Team" in q and "OWNS" in q
            if params and "asset_id" in params:
                return MockQueryResult([["secops", "Identity-SecOps", "Alice Chen", "secops@maelin.local", "auth-service"]])
            return MockQueryResult([
                ["secops", "Identity-SecOps", "Alice Chen", "secops@maelin.local", "auth-service"],
                ["payments-platform", "Payments Core Team", "Marcus Vance", "payments@maelin.local", "checkout"],
            ])

    store = Store.__new__(Store)
    store.graphs = lambda tenant: (MockTopology(), None)

    all_teams = store.team_ownership("alpha")
    assert len(all_teams) == 2
    assert all_teams[0]["team_id"] == "secops"
    assert all_teams[0]["asset_id"] == "auth-service"

    scoped = store.team_ownership("alpha", asset_id="auth-service")
    assert len(scoped) == 1
    assert scoped[0]["team_id"] == "secops"


def test_path_provenance_contains_nodes_and_relationships():
    from maelin.store import Store

    class MockQueryResult:
        def __init__(self, rows):
            self.result_set = rows

    class MockNode:
        def __init__(self, nid, props):
            self.id = nid
            self.properties = props

    class MockRel:
        def __init__(self, eid, props):
            self.id = eid
            self.properties = props

    class MockTopology:
        def ro_query(self, q, params=None):
            if "CAN_PIVOT" in q:
                return MockQueryResult([[
                    ["internet", "auth-service", "customer-db"],
                    ["p2", "p4"],
                    ["synthetic evidence 1", "synthetic evidence 2"],
                    [MockNode(1, {"id": "internet"}), MockNode(2, {"id": "auth-service"}), MockNode(3, {"id": "customer-db"})],
                    [MockRel(10, {"edge_id": "p2"}), MockRel(20, {"edge_id": "p4"})],
                ]])
            assert "DEPENDS_ON" in q
            return MockQueryResult([[
                "checkout",
                80,
                ["checkout", "auth-service"],
                [MockNode(4, {"id": "checkout"}), MockNode(2, {"id": "auth-service"})],
                [MockRel(30, {"edge_id": "d1"})],
            ]])

    store = Store.__new__(Store)
    store.graphs = lambda tenant: (MockTopology(), None)

    threat_paths = store.attack_paths("alpha", "internet", "auth-service", "customer-db")
    assert len(threat_paths) == 1
    tp = threat_paths[0]
    assert tp["nodes"] == ["internet", "auth-service", "customer-db"]
    assert tp["edges"] == ["p2", "p4"]
    assert "path_nodes" in tp
    assert "path_relationships" in tp
    assert tp["path_nodes"][0]["id"] == "internet"
    assert tp["path_relationships"][0]["edge_id"] == "p2"

    biz_paths = store.business_paths("alpha")
    assert len(biz_paths) == 1
    bp = biz_paths[0]
    assert bp["flow"] == "checkout"
    assert "path_nodes" in bp
    assert "path_relationships" in bp
    assert bp["path_nodes"][0]["id"] == "checkout"


def test_simulator_clone_name_pattern_and_cleanup():
    from maelin.simulator import run_simulation

    class MockSimClone:
        def __init__(self, name):
            self.name = name
            self.deleted = False
        def ro_query(self, q, params=None):
            if "CAN_PIVOT" in q:
                return types.SimpleNamespace(result_set=[])
            return types.SimpleNamespace(result_set=[])
        def query(self, q, params=None):
            pass
        def delete(self):
            self.deleted = True

    class MockTopo:
        def __init__(self):
            self.clone_created = None
        def copy(self, name):
            self.clone_created = MockSimClone(name)
            return self.clone_created

    class MockStore:
        def __init__(self):
            self.topo = MockTopo()
        def session_actions(self, t, s):
            return ["revoke-admin-role"]
        def interventions(self, t):
            return SCENE["actions"]
        def graphs(self, t):
            return self.topo, None
        def handoff(self, *args):
            pass

    store = MockStore()
    run_simulation(store, "alpha", "sess-1", SCENE, ["revoke-admin-role"])
    clone = store.topo.clone_created
    assert clone is not None
    # Verify clone name matches maelin_{tenant}_sim_{uuid4().hex[:8]}
    pattern = r"^maelin_alpha_sim_[0-9a-f]{8}$"
    assert re.match(pattern, clone.name), f"Clone name {clone.name!r} does not match {pattern}"
    # Verify clone was cleaned up
    assert clone.deleted is True


def test_mcp_server_exports_all_required_tools():
    try:
        import mcp
        from maelin.mcp_server import mcp as mcp_app
        tools = [t.name for t in mcp_app._tool_manager.list_tools()]
        assert "compute_asset_centrality" in tools
        assert "get_team_ownership" in tools
        assert "inspect_attack_paths" in tools
        assert "inspect_business_dependencies" in tools
        assert "recall_incident_outcomes" in tools
        assert "list_candidate_interventions" in tools
        assert "propose_containment" in tools
    except ModuleNotFoundError:
        import ast
        src = (ROOT / "maelin" / "mcp_server.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        funcs = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        assert "compute_asset_centrality" in funcs
        assert "get_team_ownership" in funcs
        assert "inspect_attack_paths" in funcs
        assert "inspect_business_dependencies" in funcs
        assert "recall_incident_outcomes" in funcs
        assert "list_candidate_interventions" in funcs
        assert "propose_containment" in funcs


def test_api_reset_demo_endpoint(monkeypatch):
    from maelin.api import api
    monkeypatch.delenv("MAELIN_OPERATOR_TOKEN", raising=False)
    monkeypatch.setenv("MAELIN_LOCAL_DEMO", "1")

    seeded = []
    class MockStore:
        def seed(self, tenant, data, reset=False):
            seeded.append((tenant, reset))

    monkeypatch.setattr("maelin.api.store", lambda: MockStore())
    client = TestClient(api)

    resp = client.post("/api/demo/reset", json={"tenant": "alpha"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "reset_successful"
    assert data["tenant"] == "alpha"
    assert seeded == [("alpha", True)]


def test_api_centrality_and_teams_endpoints(monkeypatch):
    from maelin.api import api
    monkeypatch.delenv("MAELIN_OPERATOR_TOKEN", raising=False)
    monkeypatch.setenv("MAELIN_LOCAL_DEMO", "1")

    class MockStore:
        def compute_asset_centrality(self, tenant):
            return [{"asset_id": "auth-service", "role": "authentication", "centrality_score": 0.45}]
        def team_ownership(self, tenant, asset_id=None):
            return [{"team_id": "secops", "team_name": "Identity-SecOps", "lead": "Alice", "contact": "secops@", "asset_id": "auth-service"}]

    monkeypatch.setattr("maelin.api.store", lambda: MockStore())
    client = TestClient(api)

    # Test centrality endpoint
    resp_cent = client.get("/api/centrality?tenant=alpha")
    assert resp_cent.status_code == 200
    assert "centrality" in resp_cent.json()
    assert resp_cent.json()["centrality"][0]["asset_id"] == "auth-service"

    # Test teams endpoint
    resp_teams = client.get("/api/teams?tenant=alpha")
    assert resp_teams.status_code == 200
    assert "ownership" in resp_teams.json()
    assert resp_teams.json()["ownership"][0]["team_id"] == "secops"


def test_readme_contains_ai_disclosure_and_all_core_cypher():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "AI Assistance & Verification Disclosure" in readme
    assert "Team Pied-Piper" in readme
    assert "Track 03" in readme
    assert "CALL algo.pageRank" in readme
    assert "nodes(p)" in readme
    assert "relationships(p)" in readme
    assert "(:Team)-[:OWNS]->(:Asset)" in readme
    assert "maelin_{tenant}_sim_{uuid4().hex[:8]}" in readme


def test_ui_contains_reset_button_and_wiring():
    index_html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    cockpit_js = (ROOT / "static" / "cockpit.js").read_text(encoding="utf-8")

    assert 'id="resetDemo"' in index_html
    assert "Reset demo state" in index_html
    assert "resetDemoState" in cockpit_js
    assert "/api/demo/reset" in cockpit_js
    assert "hudWired" in cockpit_js
    assert 'src="/assets/cockpit.js"' in index_html


def test_provenance_formatter_handles_zero_id_and_labels_and_relation():
    from maelin.store import _format_nodes, _format_rels
    import falkordb

    node0 = falkordb.node.Node(node_id=0, labels=["Asset"], properties={"kind": "service"})
    formatted_nodes = _format_nodes([node0])
    assert len(formatted_nodes) == 1
    assert formatted_nodes[0]["id"] == 0
    assert formatted_nodes[0]["labels"] == ["Asset"]
    assert formatted_nodes[0]["kind"] == "service"

    node1 = falkordb.node.Node(node_id=1, properties={"id": "auth-service"})
    node2 = falkordb.node.Node(node_id=2, properties={"id": "customer-db"})
    edge = falkordb.edge.Edge(src_node=node1, relation="CAN_PIVOT", dest_node=node2, edge_id=10, properties={"edge_id": "p2", "evidence": "test"})
    formatted_rels = _format_rels([edge])
    assert len(formatted_rels) == 1
    assert formatted_rels[0]["edge_id"] == "p2"
    assert formatted_rels[0]["relation"] == "CAN_PIVOT"
    assert formatted_rels[0]["from"] == "auth-service"
    assert formatted_rels[0]["to"] == "customer-db"


def test_recon_agent_records_full_cypher_provenance_query():
    from maelin.agents import ReconAgent

    recorded_handoffs = []
    class MockStore:
        def attack_paths(self, t, s, v, d):
            return [{"nodes": ["internet", "auth-service"], "edges": ["p1"], "edge_evidence": ["test"], "path_nodes": [], "path_relationships": []}]
        def business_paths(self, t):
            return [{"flow": "checkout", "value": 80, "nodes": ["checkout", "auth-service"]}]
        def handoff(self, tenant, sid, agent, status, payload):
            recorded_handoffs.append((agent, status, payload))

    agent = ReconAgent()
    agent.run(MockStore(), "alpha", "session-1", SCENE)
    assert len(recorded_handoffs) == 1
    payload = recorded_handoffs[0][2]
    assert "nodes(p) AS path_nodes" in payload["cypher_query"]
    assert "relationships(p) AS path_relationships" in payload["cypher_query"]


def test_seed_tenant_accepts_store_instance():
    from maelin.seed import seed_tenant

    seeded = []
    class MockStore:
        def seed(self, tenant, data, reset=False):
            seeded.append((tenant, reset))

    mock_store = MockStore()
    seed_tenant("alpha", reset=True, store=mock_store)
    assert seeded == [("alpha", True)]


def test_hud_layout_intel_left_legend_right():
    index_html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    cockpit_css = (ROOT / "static" / "cockpit.css").read_text(encoding="utf-8")

    # Verify #intel is in hud-tl (top-left) to avoid overlapping graph nodes
    assert 'class="hud hud-tl" id="intel"' in index_html
    # Verify .legend is in hud-tr (top-right)
    assert '<div class="hud hud-tr">' in index_html
    assert '<div class="legend">' in index_html

    # Verify CSS alignment
    assert ".hud-tl { top: 16px; left: 18px; flex-direction: column; align-items: flex-start; }" in cockpit_css
    assert ".hud-tr { top: 16px; right: 18px; align-items: center; }" in cockpit_css

