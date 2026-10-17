"""Gated integration tests: require a *real* FalkorDB server, never a mock.

Run: FALKOR_INTEGRATION=1 pytest -q tests/test_live_falkordb.py
Uses dedicated maelin_ci_* synthetic graphs. Will erase only these graphs.
"""
import os
import pytest
from pathlib import Path
import json

pytestmark=pytest.mark.skipif(os.getenv('FALKOR_INTEGRATION')!='1',reason='Requires live FalkorDB; explicitly opt in')


def test_real_cypher_traversals_and_durable_memory():
    from maelin.store import Store
    from maelin.agents import investigate
    from maelin.simulator import run_simulation
    d=json.loads((Path(__file__).parents[1]/'data'/'demo.json').read_text())
    store=Store(os.getenv('FALKOR_HOST','localhost'),os.getenv('FALKOR_PORT',6379),
                os.getenv('FALKOR_PASSWORD'))
    store.seed('ci_alpha',d,reset=True)
    store.seed('ci_beta',d,reset=True)
    cold=investigate(store,'ci_alpha',d)
    assert len(cold['paths'])==2
    assert cold['analysis']['recommended']['score']==5
    assert len(store.history('ci_alpha',cold['session_id']))==3
    sim=run_simulation(store,'ci_alpha',cold['session_id'],d,['revoke-admin-role','block-vault-pivot'])
    assert (sim['original_routes'],sim['remaining_routes'])==(2,0)
    assert sim['contained'] and sim['modeled_disruption_cost']==0
    broken=run_simulation(store,'ci_alpha',cold['session_id'],d,['revoke-admin-role'])
    assert not broken['contained'] and broken['remaining_routes']==1
    outage=run_simulation(store,'ci_alpha',cold['session_id'],d,['quarantine-auth'])
    assert outage['contained'] and outage['modeled_disruption_cost']==160
    store.record_outcome('ci_alpha',cold['session_id'],d['fingerprint'],
                         'revoke-admin-role','unexpected_outage',100,'synthetic regression test')
    store.record_outcome('ci_alpha',cold['session_id'],d['fingerprint'],
                         'revoke-admin-role','unexpected_outage',100,'duplicate POST')
    warm=investigate(store,'ci_alpha',d)
    isolated=investigate(store,'ci_beta',d)
    assert warm['analysis']['recommended']['action_ids']==['rotate-auth-credentials']
    assert len(warm['precedents'])==1, 'Duplicate POST must not duplicate memories'
    assert isolated['precedents']==[]
    assert isolated['analysis']['recommended']['score']==5
    store.inject_shadow_route('ci_alpha')
    drifted=investigate(store,'ci_alpha',d)
    assert len(drifted['paths'])==3
    assert drifted['analysis']['recommended']['action_ids']==['invalidate-attacker-session']
    old_cut=run_simulation(store,'ci_alpha',cold['session_id'],d,['revoke-admin-role','block-vault-pivot'])
    assert not old_cut['contained'] and old_cut['remaining_routes']==1
    assert not any(name.startswith('maelin_ci_alpha_sim_') for name in store.db.list_graphs())


def test_semantic_memory_and_conversation_are_real_graph_nodes():
    """A related incident retrieves discounted precedent via Cypher semantic pattern."""
    from maelin.store import Store
    from maelin.incident import select_scene
    from maelin.agents import investigate
    d=json.loads((Path(__file__).parents[1]/'data'/'demo.json').read_text())
    s=Store(os.getenv("FALKOR_HOST","localhost"),os.getenv("FALKOR_PORT",6379))
    s.seed("ci_semantic",d,reset=True)
    base=select_scene(s,"ci_semantic")
    cold=investigate(s,"ci_semantic",base)
    history=s.conversation("ci_semantic",cold["session_id"])
    assert [x["role"] for x in history]==["operator","assistant"]
    s.record_outcome("ci_semantic",cold["session_id"],base["fingerprint"],
                     "revoke-admin-role","unexpected_outage",100,
                     "synthetic report", semantic_key=base["semantic_key"])
    related=select_scene(s,"ci_semantic",vulnerable="vault-sync")
    assert related["fingerprint"]!=base["fingerprint"]
    assert related["semantic_key"]==base["semantic_key"]
    recalled=s.recall("ci_semantic",related["fingerprint"],related["semantic_key"])
    assert len(recalled)==1 and recalled[0]["match_type"]=="semantic"
    assert recalled[0]["memory_weight"]==0.25
    _,memory=s.graphs("ci_semantic")
    assert memory.ro_query("MATCH (p:Procedure) RETURN p LIMIT 1").result_set
    assert memory.ro_query("MATCH (k:SemanticPattern) RETURN k LIMIT 1").result_set


def test_second_imported_topology_uses_its_own_db_metadata():
    from maelin.store import Store
    from maelin.incident import select_scene
    from maelin.schema import validate_dataset
    d=json.loads((Path(__file__).parents[1]/'data'/'demo.json').read_text())
    d["scenario"]="Independent synthetic billing incident"
    d["fingerprint"]="incident-billing-2"
    d["vulnerable"]="vault-sync"
    d["target"]="customer-db"
    d=validate_dataset(d)
    s=Store(os.getenv("FALKOR_HOST","localhost"),os.getenv("FALKOR_PORT",6379))
    s.seed("ci_uploaded",d,reset=True)
    scene=select_scene(s,"ci_uploaded")
    assert scene["scenario"]=="Independent synthetic billing incident"
    assert scene["vulnerable"]=="vault-sync"
    assert scene["fingerprint"]=="incident-billing-2"


def test_real_concurrent_session_handoffs_are_tenant_scoped():
    from concurrent.futures import ThreadPoolExecutor
    from maelin.store import Store
    from maelin.agents import investigate
    d=json.loads((Path(__file__).parents[1]/'data'/'demo.json').read_text())
    store=Store(os.getenv('FALKOR_HOST','localhost'),os.getenv('FALKOR_PORT',6379),
                os.getenv('FALKOR_PASSWORD'))
    tenant='ci_concurrency'
    store.seed(tenant,d,reset=True)
    with ThreadPoolExecutor(max_workers=6) as pool:
        sessions=list(pool.map(lambda _:investigate(store,tenant,d),range(12)))
    ids={r['session_id'] for r in sessions}
    assert len(ids)==12
    assert all(len(store.history(tenant,sid))==3 for sid in ids)
    assert all(r['analysis']['recommended'] is not None for r in sessions)


def test_real_judge_story_is_reproducible_and_disposable():
    """Run the ENTIRE judge story, including an ablation, on actual FalkorDB."""
    from maelin.store import Store
    from maelin.judge import run
    store=Store(os.getenv('FALKOR_HOST','localhost'),os.getenv('FALKOR_PORT',6379),
                os.getenv('FALKOR_PASSWORD'))
    prior=set(store.db.list_graphs())
    evidence=run(store)
    assert evidence['initial_simulated_remaining_routes']==0
    assert evidence['memory_ablation']['recommendation_changed']
    assert evidence['old_plan_after_drift_remaining_routes']==1
    assert set(store.db.list_graphs())==prior, 'Judge proof must clean all disposable graphs'
