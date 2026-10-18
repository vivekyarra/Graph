"""Live FalkorDB tests for native algorithms, vector memory and the Company Brain.

Run: FALKOR_INTEGRATION=1 pytest -q tests/test_live_graph_intel.py
"""
import os
import pytest

pytestmark = pytest.mark.skipif(os.getenv('FALKOR_INTEGRATION') != '1',
                                reason='Requires live FalkorDB; explicitly opt in')


@pytest.fixture
def seeded():
    from maelin.store import Store
    from maelin.seed import dataset
    from maelin.schema import validate_dataset
    store = Store(os.getenv('FALKOR_HOST', 'localhost'), os.getenv('FALKOR_PORT', 6379),
                  os.getenv('FALKOR_PASSWORD'))
    store.seed('ci_intel', validate_dataset(dataset()), reset=True)
    yield store, 'ci_intel'
    for graph in store.graphs('ci_intel'):
        graph.delete()


def test_maxflow_min_cut_proves_recommended_plan_is_minimal(seeded):
    from maelin.agents import investigate
    from maelin.incident import select_scene
    store, tenant = seeded
    cut = store.min_cut(tenant, 'auth-service', 'customer-db')
    assert cut == {'max_flow': 2, 'cut_edges': ['p3', 'p5'], 'algorithm': 'algo.maxFlow'}
    # From the internet the whole topology funnels through a single pivot.
    assert store.min_cut(tenant, 'internet', 'customer-db')['max_flow'] == 1
    result = investigate(store, tenant, select_scene(store, tenant))
    assert result['analysis']['min_cut']['optimal'] is True
    assert result['analysis']['min_cut']['plan_edge_cuts'] == 2


def test_min_cut_tracks_topology_drift(seeded):
    store, tenant = seeded
    store.inject_shadow_route(tenant)
    cut = store.min_cut(tenant, 'auth-service', 'customer-db')
    assert cut['max_flow'] == 3 and len(cut['cut_edges']) == 3


def test_betweenness_chokepoints_and_blast_radius(seeded):
    store, tenant = seeded
    top = store.chokepoints(tenant)
    assert top[0] == {**top[0], 'asset_id': 'edge-gateway', 'routes': 3, 'total_routes': 3, 'route_share': 1.0}
    assert top[1]['asset_id'] == 'auth-service' and top[1]['routes'] == 2
    assert store.chokepoints(tenant) == top, 'chokepoints must be deterministic'
    assert all('betweenness' in c for c in top)
    flows = {f['flow'] for f in store.blast_radius(tenant, 'auth-service')}
    assert flows == {'checkout', 'billing', 'sign-in'}
    assert {f['flow'] for f in store.blast_radius(tenant, 'vault-sync')} == {'billing'}


def test_indexes_exist_including_vector_and_fulltext(seeded):
    store, tenant = seeded
    topology, memory = store.graphs(tenant)
    topo_idx = topology.ro_query('CALL db.indexes() YIELD label, properties, types RETURN label, properties, types').result_set
    mem_idx = memory.ro_query('CALL db.indexes() YIELD label, properties, types RETURN label, properties, types').result_set
    assert any(r[0] == 'Asset' and 'id' in r[1] for r in topo_idx)
    assert any(r[0] == 'Document' and 'FULLTEXT' in str(r[2]) for r in topo_idx)
    assert any(r[0] == 'Episode' and 'VECTOR' in str(r[2]) for r in mem_idx)
    store.ensure_indexes(tenant)  # idempotent


def test_vector_memory_recalls_structurally_similar_incident(seeded):
    from maelin.agents import investigate
    from maelin.incident import select_scene
    store, tenant = seeded
    base = select_scene(store, tenant)
    cold = investigate(store, tenant, base)
    store.record_outcome(tenant, cold['session_id'], base['fingerprint'], 'revoke-admin-role',
                         'unexpected_outage', 100, 'synthetic', semantic_key=base['semantic_key'])
    # Different entry point kind: no exact or semantic-key match, but close in vector space.
    other = select_scene(store, tenant, source='edge-gateway')
    assert other['semantic_key'] != base['semantic_key']
    recalled = store.recall(tenant, other['fingerprint'], other['semantic_key'])
    assert len(recalled) == 1
    assert recalled[0]['match_type'] == 'vector'
    assert 0.6 <= recalled[0]['similarity'] < 1
    assert recalled[0]['memory_weight'] < 0.25


def test_company_brain_answers_with_sources_and_learns_from_reports(seeded):
    from maelin import brain
    store, tenant = seeded
    answer = brain.ask(store, tenant, 'Is it safe to quarantine the auth service?')
    kinds = {s['type'] for s in answer['sources']}
    assert {'document', 'ownership', 'decision'} <= kinds
    assert answer['sources'][0]['id'] == 'rb-auth-containment'
    assert 'Identity-SecOps' in answer['answer'] and 'Rahul Iyer' in answer['answer']
    context = brain.asset_context(store, tenant, 'vault-sync')
    assert context['owners'][0]['team'] == 'Data Infrastructure'
    assert any(d['source_id'] == 'adr-014-vault-sync' for d in context['decisions'])
    action = next(a for a in store.interventions(tenant) if a['id'] == 'quarantine-gateway')
    doc = brain.write_postmortem(store, tenant, action, 'unexpected_outage', 'synthetic', 's1:quarantine-gateway', 90)
    assert brain.write_postmortem(store, tenant, action, 'unexpected_outage', 'synthetic', 's1:quarantine-gateway', 90) == doc
    fresh = brain.ask(store, tenant, 'quarantine edge gateway outage')
    assert any(s['id'] == doc for s in fresh['sources'])
    assert any(d['id'] == doc and d['origin'] == 'operator_report'
               for d in brain.asset_context(store, tenant, 'edge-gateway')['documents'])


def test_public_api_end_to_end_on_live_graph(seeded, monkeypatch):
    from fastapi.testclient import TestClient
    from maelin import api as api_module
    store, tenant = seeded
    monkeypatch.delenv('MAELIN_OPERATOR_TOKEN', raising=False)
    monkeypatch.setenv('MAELIN_LOCAL_DEMO', '1')
    monkeypatch.setattr(api_module, 'store', lambda: store)
    client = TestClient(api_module.api)
    intel = client.get(f'/api/intel?tenant={tenant}').json()
    assert intel['min_cut']['max_flow'] == 2
    run = client.post('/api/investigate', json={'tenant': tenant}).json()
    out = client.post('/api/outcome', json={'tenant': tenant, 'session_id': run['session_id'],
                                            'action_id': 'revoke-admin-role', 'outcome': 'unexpected_outage',
                                            'cost_observed': 100}).json()
    assert out['postmortem_id'].startswith('pm-auto-')
    stats = client.get(f'/api/stats?tenant={tenant}').json()
    assert stats['episodes'] == 1 and stats['sessions'] == 1
    asked = client.post('/api/brain/ask', json={'tenant': tenant, 'question': 'who owns customer-db'}).json()
    assert 'Data Infrastructure' in asked['answer']
    assert client.get(f'/api/brain/asset/nope?tenant={tenant}').status_code == 404
