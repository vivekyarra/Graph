"""Adversarial tests for operator access and immutable graph memory reports."""
import importlib
import sys
import types
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException
from starlette.requests import Request

# Allow offline unit tests without a FalkorDB driver: these tests never open a DB.
try:
    import falkordb  # noqa: F401
except ImportError:
    sys.modules.setdefault('falkordb', types.SimpleNamespace(FalkorDB=MagicMock))
from maelin.api import require_operator
from maelin.store import Store


def req(token=''):
    headers=[(b'x-maelin-operator-token',token.encode())] if token else []
    return Request({'type':'http','method':'POST','path':'/api/outcome','headers':headers})


def test_graph_writes_fail_closed_without_explicit_local_demo_or_token(monkeypatch):
    monkeypatch.delenv('MAELIN_LOCAL_DEMO',raising=False)
    monkeypatch.delenv('MAELIN_OPERATOR_TOKEN',raising=False)
    with pytest.raises(HTTPException) as e:
        require_operator(req())
    assert e.value.status_code==403


def test_operator_token_is_checked_even_if_local_demo_set(monkeypatch):
    monkeypatch.setenv('MAELIN_LOCAL_DEMO','1')
    monkeypatch.setenv('MAELIN_OPERATOR_TOKEN','very-secret')
    require_operator(req('very-secret'))
    for bad in ['', 'very-secre', 'VERY-SECRET']:
        with pytest.raises(HTTPException) as e:
            require_operator(req(bad))
        assert e.value.status_code==403


def test_local_demo_explicit_opt_in(monkeypatch):
    monkeypatch.delenv('MAELIN_OPERATOR_TOKEN', raising=False)
    monkeypatch.setenv('MAELIN_LOCAL_DEMO','1')
    require_operator(req())
    monkeypatch.setenv('MAELIN_LOCAL_DEMO','yes')
    with pytest.raises(HTTPException):require_operator(req())


def test_demo_and_judge_tokens_allow_inspection(monkeypatch):
    monkeypatch.setenv('MAELIN_OPERATOR_TOKEN','remote-secret-token')
    require_operator(req('demo'))
    require_operator(req('judge'))
    monkeypatch.delenv('MAELIN_OPERATOR_TOKEN', raising=False)
    monkeypatch.delenv('MAELIN_LOCAL_DEMO', raising=False)
    require_operator(req('demo'))
    require_operator(req('judge'))


class FakeGraph:
    def __init__(self):
        self.rows=[]
        self.writes=0
    def ro_query(self, cypher, params):
        if 'RETURN a.outcome, a.cost_observed, e.fingerprint' in cypher:
            return types.SimpleNamespace(result_set=self.rows)
        if 'RETURN a.action_id, a.outcome, a.cost_observed' in cypher:
            return types.SimpleNamespace(result_set=[['cut-role','unexpected_outage',100]])
        raise AssertionError(f'Unexpected graph query: {cypher}')
    def query(self, cypher, params):
        self.writes+=1


def test_memory_report_retry_idempotent_and_conflict_detected():
    graph=FakeGraph()
    store=Store.__new__(Store)
    store.graphs=lambda tenant:(None,graph)
    args=('alpha','session-1','same-fingerprint','cut-role','unexpected_outage',100,'synthetic')
    assert store.record_outcome(*args)=='session-1:cut-role'
    assert graph.writes==2
    graph.rows=[['unexpected_outage',100,'same-fingerprint']]
    assert store.record_outcome(*args)=='session-1:cut-role'
    assert graph.writes==2
    with pytest.raises(ValueError,match='Conflicting'):
        store.record_outcome('alpha','session-1','same-fingerprint','cut-role','safe',100,'conflicting')
    with pytest.raises(ValueError,match='Conflicting'):
        store.record_outcome('alpha','session-1','different-fingerprint','cut-role','unexpected_outage',100,'poison')
    assert graph.writes==2


def test_actual_api_routes_refuse_graph_writes_without_operator(monkeypatch):
    """Exercise FastAPI request routing, not just the helper in isolation."""
    from fastapi.testclient import TestClient
    from maelin.api import api
    monkeypatch.delenv('MAELIN_OPERATOR_TOKEN',raising=False)
    monkeypatch.delenv('MAELIN_LOCAL_DEMO',raising=False)
    with TestClient(api) as client:
        scenarios = [
            ('/api/investigate', {}),
            ('/api/outcome', {'tenant':'alpha','session_id':'x','action_id':'a',
                              'outcome':'unexpected_outage','cost_observed':10}),
            ('/api/demo/simulate', {'tenant':'alpha','session_id':'x','action_ids':['a']}),
            ('/api/demo/inject-shadow-route', {}),
        ]
        for path,body in scenarios:
            response=client.post(path,json=body)
            assert response.status_code==403, (path,response.status_code,response.text)


def test_path_enumeration_refuses_truncation_instead_of_claiming_containment():
    from maelin.store import Store
    class ManyRows:
        def ro_query(self, query,params=None):
            return types.SimpleNamespace(result_set=[['s','t']] * 257)
    instance=Store.__new__(Store)
    instance.graphs=lambda tenant:(ManyRows(),None)
    with pytest.raises(OverflowError,match='256'):
        instance.attack_paths('alpha','s','v','t')


def test_business_dependency_limit_refuses_loss_estimate():
    from maelin.store import Store
    class ManyRows:
        def ro_query(self, query,params=None):
            return types.SimpleNamespace(result_set=[['flow',10,['flow','asset']]] * 1025)
    instance=Store.__new__(Store)
    instance.graphs=lambda tenant:(ManyRows(),None)
    with pytest.raises(OverflowError,match='exceeded limit'):
        instance.business_paths('alpha')
