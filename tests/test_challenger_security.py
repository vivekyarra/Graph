"""Empirical Challenger 2 Security Boundary & Fail-Closed Adversarial Suite.

Adversarially tests:
1. Constant-time operator authentication (hmac.compare_digest) against invalid/empty/well-known tokens.
2. Public demo scope boundaries: ensure tokenless operations are strictly limited to demo tenants.
3. Tenant and asset regex injection rejection.
4. Fail-closed HTTP 503 behavior across all endpoints on database disconnection.
5. MCP tool schema boundaries and arbitrary Cypher execution rejection.
"""
import ast
import inspect
import json
import os
import re
import sys
import types
import urllib.parse
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

# Ensure FastMCP can be imported or mocked if mcp is optional in the venv
if "mcp" not in sys.modules:
    try:
        import mcp  # noqa: F401
    except ImportError:
        mock_mcp = types.ModuleType("mcp")
        mock_server = types.ModuleType("mcp.server")
        mock_fastmcp = types.ModuleType("mcp.server.fastmcp")
        class FastMCP:
            def __init__(self, name=""):
                self.name = name
                self.tools = {}
                self._tool_manager = types.SimpleNamespace(
                    list_tools=lambda: [types.SimpleNamespace(name=k) for k in self.tools.keys()]
                )
            def tool(self):
                def dec(fn):
                    self.tools[fn.__name__] = fn
                    return fn
                return dec
        mock_fastmcp.FastMCP = FastMCP
        mock_server.fastmcp = mock_fastmcp
        mock_mcp.server = mock_server
        sys.modules["mcp"] = mock_mcp
        sys.modules["mcp.server"] = mock_server
        sys.modules["mcp.server.fastmcp"] = mock_fastmcp

try:
    import falkordb  # noqa: F401
except ImportError:
    pass

from maelin.api import api, require_operator, DEMO_TENANTS, ASSET_ID
from maelin.store import Store, TENANT
from maelin import mcp_server
from maelin.seed import dataset as get_valid_dataset


def make_req(token=None):
    headers = [(b"x-maelin-operator-token", token.encode())] if token is not None else []
    return Request({"type": "http", "method": "POST", "path": "/api/investigate", "headers": headers})


# ==============================================================================
# 1. Constant-Time Operator Authentication
# ==============================================================================

def test_constant_time_operator_auth_enforcement(monkeypatch):
    configured_token = "secret-operator-token-xyz-123"
    monkeypatch.setenv("MAELIN_OPERATOR_TOKEN", configured_token)
    monkeypatch.delenv("MAELIN_PUBLIC_DEMO", raising=False)
    monkeypatch.delenv("MAELIN_LOCAL_DEMO", raising=False)

    # 1. Exact match passes
    require_operator(make_req(configured_token))

    # 2. Verify hmac.compare_digest was called with correct byte representations
    with patch("hmac.compare_digest", wraps=__import__("hmac").compare_digest) as mock_cd:
        require_operator(make_req(configured_token))
        assert mock_cd.called, "hmac.compare_digest was NOT called!"
        call_args = mock_cd.call_args[0]
        assert call_args[0] == configured_token.encode()
        assert call_args[1] == configured_token.encode()

    # 3. Invalid tokens rejected
    adversarial_tokens = [
        "",
        " ",
        "\t",
        "\x00",
        "secret-operator-token-xyz-12",
        "secret-operator-token-xyz-1234",
        "SECRET-OPERATOR-TOKEN-XYZ-123",
        "secret-operator-token-xyz-123\x00",
        "secret-operator-token-xyz-123\n",
        "admin",
        "demo",
        "judge",
        "root",
        "bearer",
        "operator",
        "123456",
        "password",
        "' OR '1'='1",
        "secret-operator-token-xyz-123-extra",
    ]
    for bad in adversarial_tokens:
        with pytest.raises(HTTPException) as exc_info:
            require_operator(make_req(bad))
        assert exc_info.value.status_code == 403

    # 4. Missing header rejected
    with pytest.raises(HTTPException) as exc_info:
        require_operator(make_req(None))
    assert exc_info.value.status_code == 403

    # 5. MAELIN_LOCAL_DEMO does not bypass a configured token
    monkeypatch.setenv("MAELIN_LOCAL_DEMO", "1")
    for bad in ["", "demo", "wrong"]:
        with pytest.raises(HTTPException) as exc_info:
            require_operator(make_req(bad))
        assert exc_info.value.status_code == 403

    # 6. Unset token fails closed by default
    monkeypatch.delenv("MAELIN_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("MAELIN_LOCAL_DEMO", raising=False)
    with pytest.raises(HTTPException) as exc_info:
        require_operator(make_req("demo"))
    assert exc_info.value.status_code == 403

    # 7. Truthy string variants for LOCAL_DEMO fail closed
    for truthy in ["yes", "true", "True", "2", "demo", "enabled"]:
        monkeypatch.setenv("MAELIN_LOCAL_DEMO", truthy)
        with pytest.raises(HTTPException) as exc_info:
            require_operator(make_req())
        assert exc_info.value.status_code == 403


# ==============================================================================
# 2. Public Demo Scope Boundaries
# ==============================================================================

def test_public_demo_scope_boundaries(monkeypatch):
    monkeypatch.delenv("MAELIN_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("MAELIN_LOCAL_DEMO", raising=False)
    monkeypatch.setenv("MAELIN_PUBLIC_DEMO", "1")

    assert DEMO_TENANTS == {"alpha", "beta"}

    # Allowed tokenlessly
    require_operator(make_req(), "alpha")
    require_operator(make_req(), "beta")
    require_operator(make_req(), None)

    # Disallowed non-demo tenants
    forbidden = [
        "gamma", "delta", "prod", "production", "internal", "corp",
        "tenant1", "ci_alpha", "judge_12345678", "__upload__", "root", "admin"
    ]
    for non_demo in forbidden:
        with pytest.raises(HTTPException) as exc_info:
            require_operator(make_req(), non_demo)
        assert exc_info.value.status_code == 403

    # Check endpoints across FastAPI app
    with TestClient(api) as client:
        assert client.post("/api/scenarios", json={"tenant": "newtenant", "dataset": {}}).status_code == 403
        assert client.get("/api/graph?tenant=gamma").status_code == 403
        assert client.get("/api/stats?tenant=gamma").status_code == 403
        assert client.get("/api/centrality?tenant=gamma").status_code == 403
        assert client.post("/api/brain/ask", json={"tenant": "gamma", "question": "Who owns auth?"}).status_code == 403
        assert client.get("/api/brain/asset/auth-service?tenant=gamma").status_code == 403
        assert client.post("/api/outcome", json={"tenant": "gamma", "session_id": "s", "action_id": "a", "outcome": "safe"}).status_code == 403
        assert client.post("/api/demo/reset", json={"tenant": "gamma"}).status_code == 403
        assert client.post("/api/demo/simulate", json={"tenant": "gamma", "session_id": "s", "action_ids": ["a"]}).status_code == 403
        assert client.post("/api/demo/inject-shadow-route", json={"tenant": "gamma"}).status_code == 403


# ==============================================================================
# 3. Tenant & Asset Regex Injection Rejection
# ==============================================================================

def test_tenant_and_asset_regex_rejection(monkeypatch):
    monkeypatch.setenv("MAELIN_LOCAL_DEMO", "1")

    malicious_tenants = [
        "alpha' OR 1=1 --", "alpha\"; DROP GRAPH g; //", "alpha\x00",
        "alpha\nbeta", "alpha\r\n", "alpha/**/beta", "../etc/passwd",
        "..\\windows", "ALPHA", "1alpha", "-alpha", "_alpha",
        "alpha$", "alpha.beta", "alpha/beta", "alpha:beta", "alpha;beta",
        "", "a" * 33, "a" * 100, "álpha", "аlpha"
    ]

    store_inst = Store.__new__(Store)
    for bad in malicious_tenants:
        assert not TENANT.fullmatch(bad)
        with pytest.raises(ValueError, match="Invalid tenant"):
            store_inst.graphs(bad)

    malicious_assets = [
        "asset' OR 1=1 --", "asset\"; MATCH (n) DETACH DELETE n; //",
        "asset\x00", "asset\nbeta", "-asset", "_asset", "ASSET",
        "asset.id", "asset/id", "../vault", "", "a" * 81, "a" * 200
    ]

    with TestClient(api) as client:
        for bad_t in ["alpha' OR 1=1", "ALPHA", "1tenant", "-bad", "a" * 33, "../escape"]:
            assert client.get(f"/api/health?tenant={bad_t}").status_code == 422
            assert client.get(f"/api/graph?tenant={bad_t}").status_code == 422
            assert client.post("/api/investigate", json={"tenant": bad_t}).status_code == 422
            assert client.post("/api/brain/ask", json={"tenant": bad_t, "question": "Who owns auth?"}).status_code == 422

        for bad_a in malicious_assets:
            safe_url_a = urllib.parse.quote(bad_a)
            res = client.get(f"/api/brain/asset/{safe_url_a}?tenant=alpha")
            if not bad_a or "/" in bad_a:
                assert res.status_code in (404, 422)
            else:
                assert res.status_code == 422

            assert client.get(f"/api/intel?tenant=alpha&vulnerable={safe_url_a}").status_code == 422
            assert client.post("/api/investigate", json={"tenant": "alpha", "source": bad_a}).status_code == 422


# ==============================================================================
# 4. Fail-Closed HTTP 503 Behavior On Database Disconnection
# ==============================================================================

def test_fail_closed_http_503_on_database_disconnection(monkeypatch):
    monkeypatch.setenv("MAELIN_LOCAL_DEMO", "1")
    import redis.exceptions
    from maelin import api as api_module

    class DisconnectedStore:
        def ready(self, *a, **k): raise redis.exceptions.ConnectionError("Connection refused")
        def topology(self, *a, **k): raise redis.exceptions.ConnectionError("Connection refused")
        def graph_scene(self, *a, **k): raise redis.exceptions.ConnectionError("Connection refused")
        def seed(self, *a, **k): raise redis.exceptions.ConnectionError("Connection refused")
        def attack_paths(self, *a, **k): raise redis.exceptions.ConnectionError("Connection refused")
        def business_paths(self, *a, **k): raise redis.exceptions.ConnectionError("Connection refused")
        def interventions(self, *a, **k): raise redis.exceptions.ConnectionError("Connection refused")
        def session_scene(self, *a, **k): raise redis.exceptions.ConnectionError("Connection refused")
        def session_actions(self, *a, **k): raise redis.exceptions.ConnectionError("Connection refused")
        def record_outcome(self, *a, **k): raise redis.exceptions.ConnectionError("Connection refused")
        def history(self, *a, **k): raise redis.exceptions.ConnectionError("Connection refused")
        def conversation(self, *a, **k): raise redis.exceptions.ConnectionError("Connection refused")
        def inject_shadow_route(self, *a, **k): raise redis.exceptions.ConnectionError("Connection refused")
        def compute_asset_centrality(self, *a, **k): raise redis.exceptions.ConnectionError("Connection refused")
        def team_ownership(self, *a, **k): raise redis.exceptions.ConnectionError("Connection refused")
        def min_cut(self, *a, **k): raise redis.exceptions.ConnectionError("Connection refused")
        def chokepoints(self, *a, **k): raise redis.exceptions.ConnectionError("Connection refused")
        def stats(self, *a, **k): raise redis.exceptions.ConnectionError("Connection refused")
        def graphs(self, *a, **k): raise redis.exceptions.ConnectionError("Connection refused")

    endpoints_to_test = [
        ("GET", "/api/health", None),
        ("GET", "/api/graph?tenant=alpha", None),
        ("GET", "/api/scene?tenant=alpha", None),
        ("POST", "/api/scenarios", {"tenant": "alpha", "dataset": get_valid_dataset()}),
        ("POST", "/api/investigate", {"tenant": "alpha"}),
        ("POST", "/api/demo/simulate", {"tenant": "alpha", "session_id": "s1", "action_ids": ["a1"]}),
        ("POST", "/api/outcome", {"tenant": "alpha", "session_id": "s1", "action_id": "a1", "outcome": "safe"}),
        ("GET", "/api/trace/session-1?tenant=alpha", None),
        ("GET", "/api/conversation/session-1?tenant=alpha", None),
        ("POST", "/api/demo/inject-shadow-route", {"tenant": "alpha"}),
        ("POST", "/api/demo/reset", {"tenant": "alpha"}),
        ("GET", "/api/centrality?tenant=alpha", None),
        ("GET", "/api/teams?tenant=alpha", None),
        ("GET", "/api/intel?tenant=alpha", None),
        ("GET", "/api/stats?tenant=alpha", None),
        ("POST", "/api/brain/ask", {"tenant": "alpha", "question": "Who owns auth?"}),
        ("GET", "/api/brain/asset/auth-service?tenant=alpha", None),
    ]

    with patch.object(api_module, "store", return_value=DisconnectedStore()):
        with TestClient(api) as client:
            for method, url, body in endpoints_to_test:
                res = client.get(url) if method == "GET" else client.post(url, json=body)
                assert res.status_code == 503, f"{method} {url} returned {res.status_code}"


# ==============================================================================
# 5. MCP Tool Schema Boundaries & Cypher Safety
# ==============================================================================

def test_mcp_tool_schema_boundaries_and_cypher_safety():
    tool_names = [
        "inspect_attack_paths", "inspect_business_dependencies", "recall_incident_outcomes",
        "list_candidate_interventions", "propose_containment", "compute_asset_centrality",
        "get_team_ownership", "compute_min_cut", "find_attack_chokepoints",
        "ask_company_brain", "get_asset_context"
    ]
    disallowed_param_names = {
        "cypher", "query", "sql", "statement", "raw", "raw_query", "eval", "code", "command", "script"
    }

    for name in tool_names:
        fn = getattr(mcp_server, name, None)
        assert fn is not None
        sig = inspect.signature(fn)
        for param_name, param in sig.parameters.items():
            assert param_name.lower() not in disallowed_param_names
            assert param.annotation != inspect.Parameter.empty

    # Audit for unparameterized queries
    import maelin.store, maelin.brain, maelin.reasoner, maelin.agents, maelin.simulator
    for mod in [maelin.store, maelin.brain, maelin.reasoner, maelin.agents, maelin.simulator, maelin.mcp_server]:
        src = inspect.getsource(mod)
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") in ("query", "ro_query"):
                if node.args and isinstance(node.args[0], ast.JoinedStr):
                    for val in node.args[0].values:
                        if isinstance(val, ast.FormattedValue):
                            assert ast.unparse(val.value) in ("typ", "self.VECTOR_DIM", "statement")

    # Spy test for Cypher parameterization
    class CypherSpyGraph:
        def __init__(self):
            self.queries = []
        def ro_query(self, cypher, params=None):
            self.queries.append((cypher, params))
            return types.SimpleNamespace(result_set=[])
        def query(self, cypher, params=None):
            self.queries.append((cypher, params))
            return types.SimpleNamespace(result_set=[])

    spy_topo = CypherSpyGraph()
    spy_mem = CypherSpyGraph()
    spy_store = Store.__new__(Store)
    spy_store.graphs = lambda tenant: (spy_topo, spy_mem)

    with patch.object(mcp_server, "store", return_value=spy_store):
        mcp_server.inspect_attack_paths("alpha", "internet' OR 1=1 //", "auth-service') RETURN 1 //", "customer-db")
        cypher, params = spy_topo.queries[-1]
        assert "internet' OR 1=1 //" not in cypher
        assert params["source"] == "internet' OR 1=1 //"

        mcp_server.recall_incident_outcomes("alpha", "fp') MATCH (n) DETACH DELETE n //")
        cypher, params = spy_mem.queries[-1]
        assert "DETACH DELETE" not in cypher
        assert params["fingerprint"] == "fp') MATCH (n) DETACH DELETE n //"

        mcp_server.get_team_ownership("alpha", "asset') RETURN 1 //")
        cypher, params = spy_topo.queries[-1]
        assert "RETURN 1 //" not in cypher
        assert params["asset_id"] == "asset') RETURN 1 //"

        with patch.object(spy_store, "graphs", return_value=(spy_topo, spy_mem)):
            mcp_server.ask_company_brain("alpha", "Who owns auth-service? ') MATCH (n) DETACH DELETE n //")
            for q, _ in spy_topo.queries:
                assert "DETACH DELETE" not in q
