"""Competition-oriented falsification tests, not staged screenshots."""
import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from maelin.agents import investigate
from maelin.logic import analyze, traversal_fallback, MAX_CANDIDATE_ACTIONS
from maelin.api import api
from test_agents import FakeFalkorStore, SCENE


def test_live_policy_ablation_on_same_graph_is_causal():
    store=FakeFalkorStore()
    cold=investigate(store,'alpha',SCENE)
    first=cold['analysis']['memory_ablation']
    assert not first['recommendation_changed']
    assert first['reports_considered']==0
    assert first['with_memory_actions']==first['without_memory_actions']
    store.report('alpha',SCENE['fingerprint'],'revoke-admin-role')
    warm=investigate(store,'alpha',SCENE)
    ab=warm['analysis']['memory_ablation']
    assert ab['recommendation_changed']
    assert ab['without_memory_actions']==first['without_memory_actions']
    assert ab['with_memory_actions']==['rotate-auth-credentials']
    assert ab['evidence_kind'].startswith('operator_report')
    assert warm['handoffs'][-1]['payload']['memory_ablation']==ab


def test_memory_isolation_ablation_proves_no_cross_tenant_contamination():
    store=FakeFalkorStore()
    store.report('alpha',SCENE['fingerprint'],'revoke-admin-role')
    a=investigate(store,'alpha',SCENE)['analysis']['memory_ablation']
    b=investigate(store,'beta',SCENE)['analysis']['memory_ablation']
    assert a['recommendation_changed'] and not b['recommendation_changed']
    assert b['reports_considered']==0


def test_badly_formed_and_enormous_action_catalogs_fail_closed():
    paths,biz=traversal_fallback(SCENE)
    base=SCENE['actions'][0]
    with pytest.raises(ValueError,match='Duplicate'):
        analyze(paths,biz,[base,dict(base)])
    with pytest.raises(OverflowError,match='48'):
        analyze(paths,biz,[dict(base,id=f'candidate_{i}') for i in range(MAX_CANDIDATE_ACTIONS+1)])
    for c in [-1,float('nan'),float('inf'),True]:
        with pytest.raises(ValueError,match='Invalid intervention cost'):
            analyze(paths,biz,[dict(base,cost=c)])
    with pytest.raises(ValueError,match='business-flow'):
        analyze(paths,[dict(biz[0],value=-40)],SCENE['actions'])
    for c in [0,4,-1]:
        with pytest.raises(ValueError,match='max_actions'):
            analyze(paths,biz,SCENE['actions'],max_actions=c)


def test_missing_threat_path_cannot_be_misrepresented_as_safety():
    _,biz=traversal_fallback(SCENE)
    analysis=analyze([],biz,SCENE['actions'])
    assert analysis['recommended'] is None
    assert analysis['reason']=='no_matching_threat_path'


def test_read_only_topology_and_handoff_are_protected_in_remote_mode(monkeypatch):
    monkeypatch.delenv('MAELIN_LOCAL_DEMO',raising=False)
    monkeypatch.setenv('MAELIN_OPERATOR_TOKEN','secret-read-write-token')
    with TestClient(api) as client:
        for url in ['/api/graph?tenant=alpha','/api/trace/any-session?tenant=beta']:
            r=client.get(url)
            assert r.status_code==403, (url,r.text)
            r=client.get(url,headers={'x-maelin-operator-token':'wrong'})
            assert r.status_code==403, (url,r.text)
        # Public liveness check still works without leaking actual paths.
        # This can respond 503 because FalkorDB is intentionally unavailable.
        assert client.get('/').status_code==200


def test_graph_write_routes_blocked_without_operator_even_if_demo_toggle_set(monkeypatch):
    monkeypatch.delenv('MAELIN_LOCAL_DEMO',raising=False)
    monkeypatch.delenv('MAELIN_OPERATOR_TOKEN',raising=False)
    monkeypatch.setenv('MAELIN_ENABLE_DEMO_MUTATIONS','1')
    with TestClient(api) as client:
        assert client.post('/api/investigate',json={}).status_code==403
        assert client.post('/api/demo/inject-shadow-route',json={}).status_code==403
        assert client.post('/api/demo/simulate',json={'session_id':'any','action_ids':['a']}).status_code==403


def test_ui_exposes_memory_ablation_and_evidence_disclaimer():
    ui=(Path(__file__).parents[1]/'static'/'index.html').read_text()
    assert 'memory_ablation' in ui
    assert 'Without memory' in ui and 'With memory' in ui
    assert 'reports are not independent forensic proof' in ui
    assert 'operatorToken' in ui
