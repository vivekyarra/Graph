"""Independent offline harness for the FalkorDB clone-backed intervention protocol.

The adapter emulates the minimum driver contract and models graph mutation; it
cannot replace the explicitly gated real-server integration test.
"""
import copy
import json
from pathlib import Path
import pytest
from maelin.logic import traversal_fallback
from maelin.simulator import run_simulation

SCENE=json.loads((Path(__file__).parents[1]/'data'/'demo.json').read_text())


class InMemoryGraphClone:
    def __init__(self, data, owner=None):
        self.data=copy.deepcopy(data)
        self.owner=owner or self
        self.deleted=False
        self.clones=[]
        self.calls=[]
    def copy(self, graphname):
        clone=InMemoryGraphClone(self.data,self.owner)
        self.owner.clones.append((graphname, clone))
        return clone
    def ro_query(self, query, params=None):
        self.calls.append(('ro',query,params))
        threat,biz=traversal_fallback(self.data)
        if 'CAN_PIVOT' in query:
            return Result([[p['nodes'],p['edges']] for p in threat])
        assert 'DEPENDS_ON' in query
        return Result([[p['flow'],p['value'],p['nodes']] for p in biz])
    def query(self, query, params):
        self.calls.append(('write',query,params))
        if 'DELETE r' in query:
            self.data['pivot_edges']=[e for e in self.data['pivot_edges'] if e['id']!=params['edge_id']]
        elif 'DETACH DELETE n' in query:
            n=params['node_id']
            self.data['assets']=[a for a in self.data['assets'] if a['id']!=n]
            self.data['pivot_edges']=[e for e in self.data['pivot_edges'] if n not in (e['from'],e['to'])]
            self.data['depends_edges']=[e for e in self.data['depends_edges'] if n not in (e['from'],e['to'])]
        else:
            raise AssertionError('unexpected mutation')
    def delete(self):
        self.deleted=True


class Result:
    def __init__(self,rows):self.result_set=rows


class StoreDouble:
    def __init__(self, scene=None):
        self.top=InMemoryGraphClone(scene or SCENE)
        self.allowed=['revoke-admin-role','block-vault-pivot','rotate-auth-credentials',
            'quarantine-auth','invalidate-attacker-session']
        self.handoffs=[]
    def session_actions(self,tenant,sid):
        return self.allowed if tenant=='alpha' and sid=='authorized-session' else []
    def interventions(self,tenant):return SCENE['actions']
    def graphs(self,tenant):return self.top,None
    def handoff(self,*args):self.handoffs.append(args)


def replay(store, actions):
    return run_simulation(store,'alpha','authorized-session',SCENE,actions)


def test_graph_replay_containment_is_based_on_modified_clone_not_original():
    store=StoreDouble()
    r=replay(store,['revoke-admin-role','block-vault-pivot'])
    assert (r['original_routes'],r['remaining_routes'])==(2,0)
    assert r['contained'] and r['modeled_disruption_cost']==0
    assert not store.top.deleted
    assert len(store.top.data['pivot_edges'])==8
    assert store.top.clones[0][1].deleted
    assert len(store.handoffs)==1 and store.handoffs[0][2]=='sandbox'
    assert store.top.clones[0][0].startswith('maelin_alpha_sim_')


def test_graph_replay_rejects_incomplete_action():
    store=StoreDouble()
    r=replay(store,['revoke-admin-role'])
    assert r['original_routes']==2 and r['remaining_routes']==1
    assert not r['contained'] and r['status']=='incomplete_containment'


def test_graph_replay_measures_customer_flow_disruption():
    store=StoreDouble()
    r=replay(store,['quarantine-auth'])
    assert r['contained']
    assert set(r['affected_flows'])=={'checkout','billing','sign-in'}
    assert r['modeled_disruption_cost']==160


def test_shadow_route_invalidates_old_complete_plan_when_graph_changes():
    scene=copy.deepcopy(SCENE)
    scene['assets'].append({'id':'shadow-role','kind':'identity','x':1,'y':1})
    scene['pivot_edges']+= [{'id':'p9','from':'auth-service','to':'shadow-role'},
                            {'id':'p10','from':'shadow-role','to':'customer-db'}]
    store=StoreDouble(scene)
    r=replay(store,['revoke-admin-role','block-vault-pivot'])
    assert (r['original_routes'],r['remaining_routes'])==(3,1)
    assert r['status']=='incomplete_containment'


def test_graph_replay_never_accepts_arbitrary_action_or_wrong_tenant():
    store=StoreDouble()
    with pytest.raises(PermissionError):
        run_simulation(store,'beta','authorized-session',SCENE,['revoke-admin-role'])
    with pytest.raises(PermissionError):
        replay(store,['malicious-action-id'])
    assert not store.top.clones


def test_graph_replay_rejects_empty_or_repeated_actions():
    store=StoreDouble()
    with pytest.raises(ValueError): replay(store,[])
    with pytest.raises(ValueError): replay(store,['revoke-admin-role']*2)
    assert not store.top.clones


def test_graph_replay_deletes_clone_on_database_error():
    store=StoreDouble()
    def broken_query(*args):raise RuntimeError('FalkorDB error')
    original_copy=store.top.copy
    def bad_copy(name):
        clone=original_copy(name)
        clone.ro_query=broken_query
        return clone
    store.top.copy=bad_copy
    with pytest.raises(RuntimeError): replay(store,['revoke-admin-role'])
    assert store.top.clones[0][1].deleted
    assert not store.handoffs
