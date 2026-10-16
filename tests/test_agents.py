import json
from pathlib import Path
from collections import defaultdict
from maelin.agents import investigate
from maelin.logic import traversal_fallback

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
        return traversal_fallback(SCENE)[0]
    def business_paths(self,t):
        self.seen_queries.append((t,'business_paths'))
        return traversal_fallback(SCENE)[1]
    def interventions(self,t):
        self.seen_queries.append((t,'interventions'))
        return SCENE['actions']
    def recall(self,t,f):
        self.seen_queries.append((t,'memory'))
        return list(self.memory[(t,f)])
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
