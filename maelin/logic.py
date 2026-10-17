"""Deterministic counterfactual safety kernel.

The database, not this module, discovers graph paths. This module computes the
consequences of candidate interventions on the graph-derived paths.
"""
from __future__ import annotations
from itertools import combinations
from math import isfinite

MAX_CANDIDATE_ACTIONS = 48  # 18,472 combinations of 1-3 actions, hard cap


def _nonnegative_number(value):
    return type(value) in (int, float) and isfinite(value) and value >= 0


def analyze(paths, business_paths, actions, precedents=(), max_actions=3):
    """Return sorted defensible plans; never call an incomplete plan 'safe'.

    paths: [{nodes:[str], edges:[str]}] verified from graph query.
    business_paths: [{flow:str, value:int, nodes:[str]}] from another query.
    precedents: [{action_id:str, outcome:'unexpected_outage'|'safe', ...}]
    """
    # Fail closed on invalid graph-derived action catalogs; never silently
    # optimize a partial or ambiguous set of interventions.
    if not (isinstance(max_actions, int) and 1 <= max_actions <= 3):
        raise ValueError("max_actions must be between 1 and 3")
    if len(actions) > MAX_CANDIDATE_ACTIONS:
        raise OverflowError("Intervention catalog exceeds bounded optimization budget (48)")
    ids = [a["id"] for a in actions]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate intervention identifiers make the recommendation ambiguous")
    if any(not _nonnegative_number(a["cost"]) for a in actions):
        raise ValueError("Invalid intervention cost: require finite non-negative numbers")
    if any(not _nonnegative_number(b["value"]) for b in business_paths):
        raise ValueError("Invalid business-flow value: require finite non-negative numbers")
    if not paths:
        return {"plans": [], "recommended": None, "reason": "no_matching_threat_path"}
    bad = {}
    for m in precedents:
        if m.get("outcome") == "unexpected_outage":
            # A single verified failure matters more than many guesses of success.
            reported = m.get("cost_observed", 60)
            loss = min(120, max(60, reported if _nonnegative_number(reported) else 60))
            bad[m["action_id"]] = min(120, bad.get(m["action_id"], 0) + loss)
    plans = []
    for n in range(1, min(max_actions, len(actions)) + 1):
        for group in combinations(actions, n):
            disabled_nodes = set().union(*(set(a["blocked_nodes"]) for a in group))
            disabled_edges = set().union(*(set(a["blocked_edges"]) for a in group))
            open_paths = [p for p in paths if not (
                disabled_nodes.intersection(p["nodes"]) or disabled_edges.intersection(p["edges"])
            )]
            if open_paths:
                continue
            # Every affected customer flow is counted once, even when multiple
            # dependency paths point to the same failing node.
            affected = {}
            for b in business_paths:
                if disabled_nodes.intersection(b["nodes"]):
                    affected[b["flow"]] = b["value"]
            active_ids = [a["id"] for a in group]
            known_failure_penalty = sum(bad.get(x, 0) for x in active_ids)
            base_cost = sum(a["cost"] for a in group)
            disruption_cost = sum(affected.values())
            plans.append({
                "action_ids": active_ids, "actions": [a["label"] for a in group],
                "blocked_nodes": sorted(disabled_nodes), "blocked_edges": sorted(disabled_edges),
                "blocked_paths": len(paths), "total_paths": len(paths),
                "affected_flows": sorted(affected), "disruption_cost": disruption_cost,
                "base_cost": base_cost, "memory_penalty": known_failure_penalty,
                "score": base_cost + disruption_cost + known_failure_penalty,
                "why": "Every known vulnerable route is cut in the bounded graph snapshot.",
                "limitations": "Not a proof against missing assets, unknown edges or exploitation outside the modeled scenario."
            })
    plans.sort(key=lambda p: (p["score"], len(p["action_ids"]), p["action_ids"]))
    # Avoid presenting redundant super-sets whose score is higher than a subset.
    pareto = []
    for p in plans:
        if any(set(q["action_ids"]).issubset(p["action_ids"]) for q in pareto):
            continue
        pareto.append(p)
    return {"plans": pareto[:15], "recommended": pareto[0] if pareto else None,
            "reason": "evaluated" if pareto else "no_complete_containment_within_action_limit"}
