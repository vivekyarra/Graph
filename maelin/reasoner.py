"""Bounded, genuine specialist LLM tool loops over actual graph evidence.

The model selects which read-only MCP tool to call; the application fixes every
argument from the verified incident context, checks each tool's returned shape,
and never lets model-generated Cypher, mutation or infrastructure commands run.
"""
import json
import os
from .llm import model_enabled, make_client, configured_model


TOOLS = {
    "inspect_attack_paths": ("paths", "Read graph-derived incident attack routes"),
    "inspect_business_dependencies": ("dependency_paths", "Read graph-derived customer impact"),
    "recall_incident_outcomes": ("precedents", "Read graph-linked prior incident experience"),
    "recall_proven_playbook": ("playbooks", "Read cross-session proven playbooks ranked by usage and MTTR"),
    "find_critical_chokepoints": ("chokepoints", "Read betweenness and attack-path severance per service"),
    "list_candidate_interventions": ("interventions", "Read graph-derived action catalog"),
}
ALLOWED = {
    "recon": ("inspect_attack_paths", "inspect_business_dependencies",
              "find_critical_chokepoints"),
    "memory": ("recall_incident_outcomes", "inspect_business_dependencies",
               "recall_proven_playbook"),
    "remediation": ("list_candidate_interventions", "inspect_business_dependencies",
                    "find_critical_chokepoints"),
}


def reason_with_tools(role, store, tenant, session_id, scene, evidence):
    """Run at most two model-led rounds and return auditable specialist conclusions.

    None means inference was not configured. A failed model step returns an
    explicit error string; it cannot override graph safety or suppress MCP failure.
    """
    if not model_enabled():
        return None
    from .agents import graph_tool
    allowed = ALLOWED[role]
    params = {
        "inspect_attack_paths": {"source":scene["source"],"vulnerable":scene["vulnerable"],
                                 "target":scene["target"]},
        "inspect_business_dependencies": {},
        "recall_incident_outcomes": {"fingerprint":scene["fingerprint"],
                                     "semantic_key":scene.get("semantic_key") or ""},
        "recall_proven_playbook": {"cve_id":scene["fingerprint"],
                                   "service_tier":(scene.get("semantic_key") or "").split("|")[1]
                                                  if (scene.get("semantic_key") or "").count("|") == 2
                                                  else "service"},
        "find_critical_chokepoints": {"vulnerable":scene["vulnerable"],
                                      "source":scene["source"], "target":scene["target"]},
        "list_candidate_interventions": {},
    }
    direct = {
        "inspect_attack_paths": lambda:store.attack_paths(tenant, scene["source"], scene["vulnerable"], scene["target"]),
        "inspect_business_dependencies": lambda:store.business_paths(tenant),
        "recall_incident_outcomes": lambda:store.recall(tenant, scene["fingerprint"],
                                                         scene.get("semantic_key")),
        "recall_proven_playbook": lambda:store.recall_proven_playbook(
            tenant, scene["fingerprint"],
            (scene.get("semantic_key") or "").split("|")[1]
            if (scene.get("semantic_key") or "").count("|") == 2 else "service"),
        "find_critical_chokepoints": lambda:store.critical_chokepoints(
            tenant, scene["vulnerable"], scene["source"], scene["target"])["chokepoints"],
        "list_candidate_interventions": lambda:store.interventions(tenant),
    }
    catalog = [{"type":"function","function":{
        "name":name, "description":TOOLS[name][1],
        "parameters":{"type":"object","properties":{},"additionalProperties":False}}}
        for name in allowed]
    instructions = (
        "You are the "+role+" specialist in a synthetic cyber-incident response swarm. "
        "Use only the read-only graph tools provided before producing a conclusion. "
        "All incident identifiers and tenant scope are fixed by the host, not the model. "
        "Interpret the graph evidence, question uncertain assumptions and explain tradeoffs; "
        "never invent assets or execute remediation. End in <=100 words."
    )
    messages = [{"role":"system","content":instructions},
                {"role":"user","content":json.dumps({"incident":scene["scenario"],
                              "alert":scene.get("alert",""), "evidence":evidence}, default=str)[:11000]}]
    selected = []
    try:
        client = make_client()
        for turn in range(3):
            response = client.chat.completions.create(
                model=configured_model(),
                messages=messages, tools=catalog,
                tool_choice="required" if turn == 0 else "auto",
                temperature=0)
            message = response.choices[0].message
            calls = message.tool_calls or []
            if not calls:
                if not selected:
                    raise ValueError("Model did not call any graph tool")
                return {"status":"reasoned_with_mcp_tools", "role":role, "tools":selected,
                        "conclusion":str(message.content or "")[:900]}
            if len(calls)>3:
                raise ValueError("Model exceeded tool-call budget")
            messages.append({"role":"assistant","content":message.content or "",
                "tool_calls":[{"id":call.id,"type":"function","function":{
                    "name":call.function.name,"arguments":call.function.arguments}} for call in calls]})
            for call in calls:
                name = call.function.name
                if name not in allowed:
                    raise ValueError("Model requested an unapproved tool")
                # Ignore all model-written arguments: a model must never pick
                # another tenant, compromised asset or fingerprint.
                records = graph_tool(store, tenant, session_id, name, params[name],
                                     direct[name], TOOLS[name][0])
                selected.append(name)
                # Evidence bounded to prevent a path explosion in model context.
                messages.append({"role":"tool","tool_call_id":call.id,
                    "content":json.dumps({"tool":name,"record_count":len(records),
                                         "sample":records[:5]},default=str)[:9000]})
        return {"status":"tool_budget_exhausted", "role":role,"tools":selected,
                "conclusion":"Verified graph tool outputs collected; deterministic safety policy remains authoritative."}
    except (ValueError, TypeError, KeyError):
        # Invalid LLM instructions are never interpreted as execution authority.
        raise
    except Exception as exc:
        if selected:
            # A database/MCP failure after any tool request is not an LLM outage.
            from .mcp_client import call_tool
            if isinstance(exc, (RuntimeError,)):
                raise
        return {"status":"model_unavailable","role":role,"tools":selected,
                "conclusion":"Model service unavailable ("+type(exc).__name__+"); deterministic graph policy remains active."}
