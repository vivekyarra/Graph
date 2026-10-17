import json
from pathlib import Path
from maelin.logic import analyze
from offline_graph import traversal_fixture

DATA=json.loads((Path(__file__).parents[1]/'data'/'demo.json').read_text())


def fixture():
    paths, business=traversal_fixture(DATA)
    return paths,business,DATA['actions']


def test_longer_compromised_paths_not_hidden_by_short_benign_route():
    paths,_,_=fixture()
    assert len(paths)==2
    assert all('auth-service' in p['nodes'] for p in paths)
    # The benign bypass p7->p8 is deliberately shorter and must not win filtering.
    assert all('p7' not in p['edges'] for p in paths)


def test_incomplete_single_edge_remediation_rejected():
    paths,biz,actions=fixture()
    result=analyze(paths,biz,actions,max_actions=1)
    ids=[p['action_ids'] for p in result['plans']]
    assert ['revoke-admin-role'] not in ids
    assert ['block-vault-pivot'] not in ids
    assert ['rotate-auth-credentials'] in ids


def test_initial_recommendation_is_surgical_pair_not_quarantine():
    paths,biz,actions=fixture()
    result=analyze(paths,biz,actions)
    assert set(result['recommended']['action_ids'])=={'revoke-admin-role','block-vault-pivot'}
    assert result['recommended']['score']==5
    assert result['recommended']['disruption_cost']==0
    quarantines=[p for p in result['plans'] if 'quarantine-auth' in p['action_ids']]
    assert quarantines and quarantines[0]['disruption_cost']==160


def test_previous_failure_changes_later_ranking():
    paths,biz,actions=fixture()
    cold=analyze(paths,biz,actions)
    warm=analyze(paths,biz,actions,[{'action_id':'revoke-admin-role','outcome':'unexpected_outage'}])
    assert cold['recommended']['action_ids']!=warm['recommended']['action_ids']
    assert warm['recommended']['action_ids']==['rotate-auth-credentials']
    assert warm['recommended']['score']==6


def test_success_does_not_overconfidently_override_safety():
    paths,biz,actions=fixture()
    safe=analyze(paths,biz,actions,[{'action_id':'quarantine-auth','outcome':'safe'}])
    assert 'quarantine-auth' not in safe['recommended']['action_ids']


def test_same_customer_flow_not_counted_multiple_times():
    paths,biz,actions=fixture()
    # duplicate dependency path should not double-charge checkout
    double=analyze(paths,biz+biz,actions,max_actions=1)
    quarantine=[p for p in double['plans'] if p['action_ids']==['quarantine-auth']][0]
    assert quarantine['disruption_cost']==160


def test_no_matching_path_is_not_certified_safe():
    _,biz,actions=fixture()
    result=analyze([],biz,actions)
    assert result['recommended'] is None
    assert result['reason']=='no_matching_threat_path'


def test_requires_all_known_paths_be_blocked():
    paths,biz,actions=fixture()
    plans=analyze(paths,biz,actions)['plans']
    for plan in plans:
        group=[a for a in actions if a['id'] in plan['action_ids']]
        nodes=set().union(*(set(a['blocked_nodes']) for a in group))
        edges=set().union(*(set(a['blocked_edges']) for a in group))
        assert all(set(p['nodes']) & nodes or set(p['edges']) & edges for p in paths)


def test_missing_single_route_generates_different_answer_and_is_not_hardcoded():
    paths,biz,actions=fixture()
    only_p1=[p for p in paths if 'p3' in p['edges']]
    result=analyze(only_p1,biz,actions)
    assert result['recommended']['action_ids']==['revoke-admin-role']


def test_topology_drift_invalidates_old_cut_and_forces_new_plan():
    import copy
    scene=copy.deepcopy(DATA)
    scene['assets'].append({'id':'shadow-role','kind':'identity','x':603,'y':225})
    scene['pivot_edges']+=[
        {'id':'p9','from':'auth-service','to':'shadow-role'},
        {'id':'p10','from':'shadow-role','to':'customer-db'}]
    paths,biz=traversal_fixture(scene)
    assert len(paths)==3
    cold=analyze(paths,biz,scene['actions'])
    assert cold['recommended']['action_ids']==['invalidate-attacker-session']
    assert cold['recommended']['score']==12
    assert not any(set(p['action_ids'])=={'revoke-admin-role','block-vault-pivot'} for p in cold['plans'])
