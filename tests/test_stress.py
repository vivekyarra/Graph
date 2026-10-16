"""Repeatable adversarial checks against a separately written brute-force oracle."""
from itertools import combinations
from random import Random
from maelin.logic import analyze


def exhaustive_oracle(paths, business, actions, bad):
    best=None
    for size in range(1, min(3,len(actions))+1):
        for group in combinations(actions,size):
            killed_nodes={n for a in group for n in a['blocked_nodes']}
            killed_edges={e for a in group for e in a['blocked_edges']}
            if any(not (set(p['nodes']) & killed_nodes or set(p['edges']) & killed_edges) for p in paths):
                continue
            losses={b['flow']:b['value'] for b in business if set(b['nodes']) & killed_nodes}
            penalties=sum(60 for a in group if a['id'] in bad)
            score=sum(a['cost'] for a in group)+sum(losses.values())+penalties
            label=sorted(a['id'] for a in group)
            trial=(score,size,label)
            if best is None or trial<best:
                best=trial
    return best


def test_randomized_optimizer_agrees_with_independent_oracle():
    rng=Random(20261016)
    for case in range(5000):
        n_routes=rng.randint(1,6)
        paths=[{'nodes':['internet',f'pivot-{i}','db'],
                'edges':[f'x{i}']} for i in range(n_routes)]
        actions=[]
        for i in range(rng.randint(2,9)):
            edges=[f'x{j}' for j in range(n_routes) if rng.random()<.42]
            nodes=['pivot-'+str(j) for j in range(n_routes) if rng.random()<.08]
            actions.append({'id':f'a{i}','label':f'Action {i}',
                'blocked_nodes':nodes,'blocked_edges':edges,'cost':rng.randint(1,10)})
        actions.append({'id':'emergency','label':'Emergency','blocked_nodes':['internet'],
                        'blocked_edges':[],'cost':25})
        business=[{'flow':f'flow-{i}','value':rng.randint(1,20),
                   'nodes':['flow-'+str(i), 'internet' if rng.random()<.2 else 'service']}
                  for i in range(rng.randint(1,5))]
        bad={a['id'] for a in actions if rng.random()<.1}
        prior=[{'action_id':x,'outcome':'unexpected_outage'} for x in bad]
        result=analyze(paths,business,actions,prior)
        oracle=exhaustive_oracle(paths,business,actions,bad)
        assert result['recommended'] is not None, case
        assert result['recommended']['score']==oracle[0], (case, result['recommended'], oracle)
        assert len(result['recommended']['action_ids'])==oracle[1], case
        assert sorted(result['recommended']['action_ids'])==oracle[2], case
