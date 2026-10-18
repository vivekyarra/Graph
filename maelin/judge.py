"""Reproducible real-FalkorDB proof: Track 01 + Track 02, never production.

    python -m maelin.judge --output judge-proof.json

Creates uniquely named disposable SYNTHETIC graphs, runs a deterministic
cold→replay→memory→drift sequence, then deletes both graphs even on error.
Never calls cloud APIs and never asserts real-world exploit validation.
"""
from __future__ import annotations
import argparse
import json
import os
import time
import uuid
from pathlib import Path

from .agents import investigate
from .brain import ask, write_postmortem
from .incident import select_scene
from .schema import validate_dataset
from .seed import dataset
from .simulator import run_simulation
from .store import Store


def run(store: Store) -> dict:
    tenant = "judge_" + uuid.uuid4().hex[:8]
    data = validate_dataset(dataset())
    started = time.monotonic()
    try:
        store.seed(tenant, data, reset=False)
        cold = investigate(store, tenant, data)
        assert len(cold["paths"]) == 2, "Expected 2 graph-derived threat routes"
        plan = cold["analysis"]["recommended"]
        assert plan and set(plan["action_ids"]) == {"revoke-admin-role", "block-vault-pivot"}
        assert len(cold["handoffs"]) == 3, "Graph-stored specialist handoffs missing"
        sim = run_simulation(store, tenant, cold["session_id"], data, plan["action_ids"])
        assert sim["contained"] and sim["remaining_routes"] == 0
        assert sim["modeled_disruption_cost"] == 0
        # A human-supplied report, explicitly NOT an independently observed outage.
        store.record_outcome(tenant, cold["session_id"], data["fingerprint"],
                             "revoke-admin-role", "unexpected_outage", 100,
                             "synthetic judge harness operator report")
        warm = investigate(store, tenant, data)
        ablation = warm["analysis"]["memory_ablation"]
        assert ablation["recommendation_changed"]
        assert warm["analysis"]["recommended"]["action_ids"] == ["rotate-auth-credentials"]
        assert ablation["without_memory_actions"] == plan["action_ids"]
        assert len(store.history(tenant, warm["session_id"])) == 3
        # Track 01: native algo.maxFlow proves the plan cuts the minimum number of pivots.
        min_cut = cold["analysis"]["min_cut"]
        assert min_cut["max_flow"] == 2 and min_cut["optimal"]
        # Track 02: a structurally similar (not identical) incident recalls the
        # report through the FalkorDB vector index.
        scene = select_scene(store, tenant)
        store.record_outcome(tenant, cold["session_id"], data["fingerprint"],
                             "quarantine-auth", "unexpected_outage", 120,
                             "synthetic judge harness operator report",
                             semantic_key=scene["semantic_key"])
        similar = select_scene(store, tenant, source="edge-gateway")
        vector_hits = [m for m in store.recall(tenant, similar["fingerprint"], similar["semantic_key"])
                       if m["match_type"] == "vector"]
        assert vector_hits, "Vector index recall missing"
        # Track 03: the report becomes a cited postmortem the Company Brain can answer from.
        action = next(a for a in store.interventions(tenant) if a["id"] == "quarantine-auth")
        doc = write_postmortem(store, tenant, action, "unexpected_outage", "judge harness",
                               cold["session_id"] + ":quarantine-auth", 120)
        brain = ask(store, tenant, "Is it safe to quarantine auth-service?")
        assert any(s["id"] == doc for s in brain["sources"])
        assert {"document", "ownership", "decision"} <= {s["type"] for s in brain["sources"]}
        # Topology drift makes the old once-complete action set incomplete.
        store.inject_shadow_route(tenant)
        drift = investigate(store, tenant, data)
        assert len(drift["paths"]) == 3
        old_replay = run_simulation(store, tenant, cold["session_id"], data, plan["action_ids"])
        assert not old_replay["contained"] and old_replay["remaining_routes"] == 1
        assert drift["analysis"]["recommended"]["action_ids"] == ["invalidate-attacker-session"]
        result = {
            "scope": "SYNTHETIC ONLY; no real exploit, no production remediation",
            "database": "real FalkorDB driver; Cypher traversals, memory handoffs, native graph copy",
            "tenant": "ephemeral synthetic judge namespace",
            "initial_known_attack_routes": len(cold["paths"]),
            "initial_plan_actions": plan["action_ids"],
            "initial_simulated_remaining_routes": sim["remaining_routes"],
            "initial_simulated_customer_impact": sim["modeled_disruption_cost"],
            "durable_handoffs": len(cold["handoffs"]),
            "reported_outcome_evidence": "operator_report (synthetic, unverified)",
            "memory_ablation": ablation,
            "min_cut_algo_maxflow": {"max_flow": min_cut["max_flow"], "cut_edges": min_cut["cut_edges"],
                                     "plan_is_minimal": min_cut["optimal"]},
            "vector_memory_recall": {"similarity": vector_hits[0]["similarity"],
                                     "weight": vector_hits[0]["memory_weight"]},
            "company_brain": {"sources": len(brain["sources"]), "auto_postmortem": doc},
            "after_topology_drift_routes": len(drift["paths"]),
            "old_plan_after_drift_remaining_routes": old_replay["remaining_routes"],
            "revised_plan_after_drift": drift["analysis"]["recommended"]["action_ids"],
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
        return result
    finally:
        # Best effort cleanup includes partial seeding failures, when only one
        # of the two graphs may have been created. Never touch any other tenant.
        present = set(store.db.list_graphs())
        topology, memory = store.graphs(tenant)
        if f"maelin_{tenant}_topology" in present:
            topology.delete()
        if f"maelin_{tenant}_memory" in present:
            memory.delete()
        # This is a deterministic evidence harness, not a telemetry exporter.


def main():
    p=argparse.ArgumentParser(description="Reproducible empirical verification harness on running FalkorDB")
    p.add_argument('--output', type=Path, help="Optional path for a machine-readable proof JSON")
    args=p.parse_args()
    store=Store(os.getenv('FALKOR_HOST','localhost'),os.getenv('FALKOR_PORT','6379'),
                os.getenv('FALKOR_PASSWORD'))
    result=run(store)
    if args.output:
        args.output.write_text(json.dumps(result,indent=2)+"\n",encoding='utf-8')
    print(json.dumps(result,indent=2))
    print("PASS: real-graph traversal, clone replay, persisted handoffs, memory ablation and drift")


if __name__=='__main__':
    main()
