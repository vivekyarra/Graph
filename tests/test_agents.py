import json
from pathlib import Path
from collections import defaultdict
from maelin.agents import investigate
from offline_graph import traversal_fixture

SCENE=json.loads((Path(__file__).parents[1]/'data'/'demo.json').read_text())


class FakeFalkorStore:
    """Strict in-memory contract fake used ONLY by tests, never the API."""
    def __init__(self):
        self.sessions={}
        self.memory=defaultdict(list)
        self.seen_queries=[]
    def ready(self,t):return True
    def new_session(self,t,f):
        sid=f'{t}-{len(self.sessions)}'
        self.sessions[(t,sid)]={'allowed':[], 'handoffs':[]}
        return sid
    def attack_paths(self,t,s,v,d):
        self.seen_queries.append((t,'attack_paths'))
        return traversal_fixture(SCENE)[0]
    def business_paths(self,t):
        self.seen_queries.append((t,'business_paths'))
        return traversal_fixture(SCENE)[1]
    def interventions(self,t):
        self.seen_queries.append((t,'interventions'))
        return SCENE['actions']
    def recall(self, t, f, component=None):
        self.seen_queries.append((t, 'memory'))
        res = list(self.memory[(t, f)])
        if not res and component:
            for (ten, fp), items in self.memory.items():
                if ten == t and (component in fp):
                    res.extend(items)
        return res
    def handoff(self,t,s,a,st,p):
        self.sessions[(t,s)]['handoffs'].append(dict(agent=a,status=st,payload=p))
    def proposed(self,t,s,actions):self.sessions[(t,s)]['allowed']=actions
    def history(self,t,s):return self.sessions[(t,s)]['handoffs']
    def session_actions(self,t,s):return self.sessions[(t,s)]['allowed']
    def report(self,t,f,action):
        self.memory[(t,f)].append({'action_id':action,'outcome':'unexpected_outage'})


def test_three_agent_handoffs_and_memory_change():
    store=FakeFalkorStore()
    a=investigate(store,'alpha',SCENE)
    assert [h['agent'] for h in a['handoffs']]==['recon','memory','remediation']
    assert a['session_id'].startswith('alpha')
    store.report('alpha',SCENE['fingerprint'],'revoke-admin-role')
    b=investigate(store,'alpha',SCENE)
    assert b['analysis']['recommended']['action_ids']==['rotate-auth-credentials']
    assert b['precedents'][0]['outcome']=='unexpected_outage'
    assert 'revoke-admin-role' in store.session_actions('alpha',a['session_id'])
    # Proposals are not arbitrary narrative: a proposed action is actually in the plan.
    assert store.session_actions('alpha',a['session_id'])


def test_isolated_tenant_does_not_inherit_failed_memory():
    store=FakeFalkorStore()
    store.report('alpha',SCENE['fingerprint'],'revoke-admin-role')
    alpha=investigate(store,'alpha',SCENE)
    beta=investigate(store,'beta',SCENE)
    assert alpha['analysis']['recommended']['action_ids']==['rotate-auth-credentials']
    assert set(beta['analysis']['recommended']['action_ids'])=={'revoke-admin-role','block-vault-pivot'}
    assert not beta['precedents']
    assert {(t,q) for t,q in store.seen_queries if t=='beta'}=={
        ('beta','attack_paths'),('beta','business_paths'),('beta','interventions'),('beta','memory')}


def test_agent_reasoning_and_cypher_in_handoffs():
    store = FakeFalkorStore()
    custom_scene = dict(SCENE)
    custom_scene["source"] = "internet"
    custom_scene["vulnerable"] = "auth-service"
    custom_scene["target"] = "customer-db"
    res = investigate(store, "alpha", custom_scene)
    handoffs = res["handoffs"]

    # Verify all 3 specialist agents attached structured reasoning
    recon_h = next(h for h in handoffs if h["agent"] == "recon")
    assert "agent_reasoning" in recon_h["payload"]
    assert "cypher_query" in recon_h["payload"]
    assert "MATCH p=" in recon_h["payload"]["cypher_query"]
    assert "auth-service" in recon_h["payload"]["cypher_query"]

    memory_h = next(h for h in handoffs if h["agent"] == "memory")
    assert "agent_reasoning" in memory_h["payload"]

    remediation_h = next(h for h in handoffs if h["agent"] == "remediation")
    assert "agent_reasoning" in remediation_h["payload"]
    assert res["analysis"]["agent_reasoning"]


def test_associative_memory_recall_fallback():
    store = FakeFalkorStore()
    # Store memory under a fingerprint containing "auth-service"
    store.report("alpha", "fp-incident-auth-service-compromise", "revoke-admin-role")

    # Investigate a scene with a novel fingerprint but referencing auth-service as vulnerable component
    scene = dict(SCENE)
    scene["fingerprint"] = "completely-novel-fp-xyz"
    scene["vulnerable"] = "auth-service"

    res = investigate(store, "alpha", scene)
    # Memory agent should associatively recall the prior experience by component name
    assert len(res["precedents"]) == 1
    assert res["precedents"][0]["action_id"] == "revoke-admin-role"

