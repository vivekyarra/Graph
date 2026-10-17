"""Three bounded specialist agents, sharing context only through FalkorDB.

Deterministic specialist policies are disclosed: these are tool-using agents,
not three separate LLM calls masquerading as experts. Optional language-model
integration can be layered on top without granting it direct Cypher access.
"""
from .logic import analyze
from .llm import adjudicate


class ReconAgent:
    name = "recon"
    def run(self, store, tenant, sid, scene):
        paths = store.attack_paths(tenant, scene["source"], scene["vulnerable"], scene["target"])
        business = store.business_paths(tenant)
        store.handoff(tenant, sid, self.name, "mapped", {
            "threat_paths":len(paths), "business_dependencies":len(business),
            "verified_path_payload":paths,"customer_dependency_payload":business,
            "source":scene["source"], "vulnerable":scene["vulnerable"], "target":scene["target"],
            "query_limits":"max depth 7, max 256 threat paths, max 1024 business paths"})
        return paths, business


class MemoryAgent:
    name = "memory"
    def run(self, store, tenant, sid, scene):
        # The next specialist MUST retrieve the Recon handoff from the durable
        # memory graph; no hidden in-process shared state between specialists.
        ledger = store.history(tenant, sid)
        if not any(h["agent"]=="recon" and h["status"]=="mapped" for h in ledger):
            raise RuntimeError("Recon graph handoff missing; cannot coordinate")
        prior = store.recall(tenant, scene["fingerprint"])
        store.handoff(tenant, sid, self.name, "recalled", {
            "fingerprint":scene["fingerprint"],"precedents":len(prior),
            "reported_failures":sum(x["outcome"]=="unexpected_outage" for x in prior),
            "recalled_experiences":prior})
        return prior


class RemediationAgent:
    name = "remediation"
    def run(self, store, tenant, sid, scene, goal):
        # Both path evidence and learned procedural constraints arrive through
        # an explicit persisted graph handoff, NOT Python arguments.
        ledger=store.history(tenant,sid)
        recon=next((h for h in ledger if h["agent"]=="recon"), None)
        memory=next((h for h in ledger if h["agent"]=="memory"), None)
        if not recon or not memory:
            raise RuntimeError("Required graph handoff missing: refusing remediation")
        paths=recon["payload"]["verified_path_payload"]
        business=recon["payload"]["customer_dependency_payload"]
        precedent=memory["payload"]["recalled_experiences"]
        interventions = store.interventions(tenant)
        result = analyze(paths, business, interventions, precedent)
        # Controlled ablation: same live graph and action catalog, with the
        # recalled memory removed. This is a causal policy comparison, not a
        # claim that the operator's report is independently verified.
        cold_policy = analyze(paths, business, interventions, ())
        cold = cold_policy["recommended"]
        warm = result["recommended"]
        result["memory_ablation"] = {
            "without_memory_actions": cold["action_ids"] if cold else None,
            "without_memory_score": cold["score"] if cold else None,
            "with_memory_actions": warm["action_ids"] if warm else None,
            "with_memory_score": warm["score"] if warm else None,
            "recommendation_changed": bool(cold and warm and cold["action_ids"] != warm["action_ids"]),
            "reports_considered": len(precedent),
            "evidence_kind": "operator_report, not independent forensic verification",
            "interpretation": "Same topology, same candidate set; only previous operator reports were removed.",
        }
        naive = next((a for a in interventions if a["id"] == "quarantine-auth"), None)
        baseline = analyze(paths, business, [naive], ()) if naive else None
        result["naive_emergency_brake"] = baseline["recommended"] if baseline else None
        result["agent_choice"] = adjudicate(result["plans"],goal)
        # The approved action IDs are persisted as a session-scoped graph handoff.
        offered = sorted(set(id for p in result["plans"] for id in p["action_ids"]))
        store.proposed(tenant, sid, offered)
        store.handoff(tenant, sid, self.name, "proposed", {
            "candidate_plans":len(result["plans"]),
            "recommended":result["recommended"]["action_ids"] if result["recommended"] else None,
            "outcome":result["reason"],"agent_choice":result["agent_choice"],
            "memory_ablation":result["memory_ablation"]})
        return result


def investigate(store, tenant, scene, goal="minimize customer disruption"):
    if not store.ready(tenant):
        raise LookupError("Graph not seeded: run python -m maelin.seed")
    sid = store.new_session(tenant, scene["fingerprint"])
    if hasattr(store, "set_session_scene"):
        store.set_session_scene(tenant, sid, scene)
    paths, business = ReconAgent().run(store,tenant,sid,scene)
    memory = MemoryAgent().run(store,tenant,sid,scene)
    result = RemediationAgent().run(store,tenant,sid,scene,goal)
    return {"session_id":sid,"scene":scene["scenario"],"paths":paths,"business_paths":business,
            "precedents":memory,"analysis":result,"handoffs":store.history(tenant,sid),
            "safety":"Simulation and recommendations only. Never modifies infrastructure.",
            "scope":"Synthetic graph snapshot; bounded paths. Unknown topology is not proof of safety."}
