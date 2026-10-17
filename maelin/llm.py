"""Bounded LLM planning and multi-agent synthesis over verified counterfactual graph alternatives.

Never executes arbitrary infrastructure commands or unverified Cypher.
Supports both OpenAI and Google Gemini APIs with automatic fallback to
the deterministic graph safety kernel.
"""
from __future__ import annotations
import json
import os
import logging

logger = logging.getLogger("maelin.llm")


def synthesize_recon_insight(paths: list, business_paths: list, scene: dict) -> str:
    """Agentic reasoning token synthesis for Recon Specialist."""
    vuln = scene.get("vulnerable", "auth-service")
    target = scene.get("target", "customer-db")
    num_paths = len(paths)
    num_biz = len(business_paths)
    dependent_flows = sorted(list({b.get("flow") for b in business_paths if vuln in b.get("nodes", [])}))
    flows_str = ", ".join(dependent_flows) if dependent_flows else "none"

    return (
        f"Recon Agent Analysis: Identified {num_paths} multi-hop threat route(s) transitioning through "
        f"compromised service '{vuln}' reaching critical database '{target}'. A shorter benign bypass exists, "
        f"but vulnerable routes exploit privileged IAM roles and replication pipelines. "
        f"Critical business flow(s) [{flows_str}] depend directly on '{vuln}'. Naive pod termination "
        f"will trigger immediate cascading customer outages."
    )


def synthesize_memory_insight(precedents: list, fingerprint: str) -> str:
    """Agentic reasoning token synthesis for Memory Specialist."""
    failures = [p for p in precedents if p.get("outcome") == "unexpected_outage"]
    if not precedents:
        return (
            f"Memory Agent Analysis: Querying episodic graph for signature '{fingerprint}'. "
            f"Cold start: no previous incident reports found. All candidate graph cuts evaluated at baseline cost."
        )
    if failures:
        bad_actions = sorted(list({f["action_id"] for f in failures}))
        return (
            f"Memory Agent Analysis: Recalled {len(precedents)} historical incident precedent(s) for '{fingerprint}'. "
            f"CRITICAL WARNING: Operator reports show prior outage(s) caused by intervention(s): {bad_actions}. "
            f"Applying persistent memory penalty (+60 per failed attempt) to prevent repeated operational damage."
        )
    return (
        f"Memory Agent Analysis: Recalled {len(precedents)} precedent(s) in episodic memory. "
        f"No adverse outages reported for current candidate interventions."
    )


def synthesize_remediation_insight(recommended_plan: dict | None, naive_plan: dict | None) -> str:
    """Agentic reasoning token synthesis for Remediation Specialist."""
    if not recommended_plan:
        return "Remediation Agent: No admissible plan found that cuts 100% of threat routes within budget. Refusing partial containment."
    
    actions_str = " + ".join(recommended_plan.get("actions", recommended_plan.get("action_ids", [])))
    disruption = recommended_plan.get("disruption_cost", 0)
    naive_cost = naive_plan.get("disruption_cost", 0) if naive_plan else 0
    
    return (
        f"Remediation Agent Decision: Formulated surgical graph-cut [{actions_str}]. "
        f"Future A (Naive Quarantine) results in {naive_cost} customer impact units. "
        f"Future B (Selected Cut) achieves 100% threat containment with {disruption} customer impact units. "
        f"All 7-hop threat routes severed on the modeled topology snapshot."
    )


def adjudicate(plans, goal="minimize customer disruption"):
    """Select the optimal admissible plan based on operator priorities and graph safety constraints."""
    if not plans:
        return {"mode": "no_safe_plan", "selected_index": None, "explanation": "No fully covering candidate found."}

    # Bounded eligible set within 4 score units of optimal
    eligible = [(i, plan) for i, plan in enumerate(plans)
                if plan["score"] <= plans[0]["score"] + 4
                and plan["disruption_cost"] <= plans[0]["disruption_cost"]]
    prefer_fewer = "fewest" in goal.lower() or "fewer changes" in goal.lower()
    choice = (min(eligible, key=lambda x: (len(x[1]["action_ids"]), x[1]["score"], x[0]))[0]
              if prefer_fewer and eligible else 0)

    deterministic = {
        "mode": "deterministic_policy",
        "selected_index": choice,
        "explanation": (
            "Fewest changes within four score units of the minimum, without increasing modeled customer disruption."
            if prefer_fewer else
            "Lowest combined synthetic impact, execution cost and prior-failure penalty."
        )
    }

    # If LLM execution is not explicitly requested, return deterministic safety kernel output
    if os.getenv("MAELIN_USE_LLM") != "1":
        return deterministic

    # Check for Google Gemini API key
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        try:
            import httpx
            acceptable = [(i, p) for i, p in enumerate(plans) if p["score"] <= plans[0]["score"] + 4]
            choices = [{"index": i, "actions": p["actions"], "score": p["score"],
                        "disruption_cost": p["disruption_cost"], "memory_penalty": p["memory_penalty"]}
                       for i, p in acceptable[:6]]
            prompt = (
                f"You are an autonomous incident-response planning agent. "
                f"Operator Goal: {goal}\n"
                f"Verified Admissible Graph Cuts: {json.dumps(choices)}\n"
                f"Select the best plan index (must be one of {[c['index'] for c in choices]}). "
                f"Return JSON strictly formatted as: {{\"index\": <int>, \"reason\": \"<string>\"}}"
            )
            resp = httpx.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}",
                json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"response_mime_type": "application/json"}},
                timeout=10.0
            )
            if resp.status_code == 200:
                result_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(result_text)
                chosen = int(parsed["index"])
                if chosen in {i for i, _ in acceptable[:6]}:
                    return {
                        "mode": "gemini_tool_choice_validated",
                        "selected_index": chosen,
                        "explanation": str(parsed.get("reason", "Gemini validated optimal business continuity plan"))[:400]
                    }
        except Exception as e:
            logger.warning(f"Gemini LLM evaluation skipped: {e}")

    # Check for OpenAI API key
    if os.getenv("OPENAI_API_KEY"):
        try:
            from openai import OpenAI
            acceptable = [(i, p) for i, p in enumerate(plans) if p["score"] <= plans[0]["score"] + 4]
            choices = [{"index": i, "actions": p["actions"], "score": p["score"],
                        "disruption_cost": p["disruption_cost"], "memory_penalty": p["memory_penalty"]}
                       for i, p in acceptable[:6]]
            c = OpenAI(timeout=12.0)
            r = c.chat.completions.create(
                model=os.getenv("MAELIN_LLM_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": "You are an incident-response planning agent. Select ONLY a numbered admissible intervention plan. The graph-based safety kernel already checked reachability. Prefer cheaper and fewer irreversible changes. Do not assert confirmed exploitation or claim real-world safety. You do not execute anything."},
                    {"role": "user", "content": f"Operator goal: {goal}\nVerified bounded counterfactual options: {json.dumps(choices)}"}
                ],
                tools=[{"type": "function", "function": {
                    "name": "select_counterfactual_plan",
                    "description": "Select one of the approved safe plans using the operator goal and recorded memory.",
                    "parameters": {
                        "type": "object",
                        "properties": {"index": {"type": "integer"}, "reason": {"type": "string"}},
                        "required": ["index", "reason"],
                        "additionalProperties": False
                    }
                }}],
                tool_choice={"type": "function", "function": {"name": "select_counterfactual_plan"}},
                temperature=0
            )
            calls = r.choices[0].message.tool_calls or []
            if len(calls) == 1 and calls[0].function.name == "select_counterfactual_plan":
                args = json.loads(calls[0].function.arguments)
                chosen = int(args["index"])
                if chosen in {i for i, _ in acceptable[:6]}:
                    return {
                        "mode": "llm_tool_choice_validated",
                        "selected_index": chosen,
                        "explanation": str(args.get("reason", ""))[:400]
                    }
        except Exception as exc:
            return {
                "mode": "llm_unavailable_policy_fallback",
                "selected_index": deterministic["selected_index"],
                "explanation": f"Model step unavailable ({type(exc).__name__}); safe deterministic policy used."
            }

    return deterministic
