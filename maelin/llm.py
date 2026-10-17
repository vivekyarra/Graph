"""Optional bounded LLM planning over verified counterfactual alternatives.

Never executes infrastructure commands or writes Cypher. Model output is
untrusted and validated against the deterministic safety kernel.
"""
import json
import os


def model_enabled():
    return bool(os.getenv("OPENAI_API_KEY") or os.getenv("MAELIN_LLM_BASE_URL")) and os.getenv("MAELIN_USE_LLM", "auto").lower() not in {"0", "off", "false"}


def make_client():
    from openai import OpenAI
    options = {"timeout": 12.0, "api_key": os.getenv("OPENAI_API_KEY") or "ollama-local"}
    if os.getenv("MAELIN_LLM_BASE_URL"):
        options["base_url"] = os.environ["MAELIN_LLM_BASE_URL"]
    return OpenAI(**options)


def narrate(role, evidence):
    """Evidence-bound specialist interpretation, never graph writes or unsafe actions."""
    if not model_enabled():
        return None
    try:
        response = make_client().chat.completions.create(
            model=os.getenv("MAELIN_LLM_MODEL", "gpt-4o-mini"),
            messages=[
                {"role":"system", "content": (
                    "You are a specialist incident-response reasoning agent. Your role: " + role +
                    ". Interpret only supplied SYNTHETIC graph evidence, acknowledge missing facts, "
                    "and propose one verification question. Limit to 75 words. Never invent findings or perform changes.")},
                {"role":"user", "content":json.dumps(evidence)}
            ], temperature=0)
        return str(response.choices[0].message.content or "")[:600]
    except Exception as exc:
        return "LLM unavailable (" + type(exc).__name__ + "); verified graph evidence remains authoritative."




def adjudicate(plans, goal="minimize customer disruption"):
    if not plans:
        return {"mode":"no_safe_plan","selected_index":None,"explanation":"No fully covering candidate found."}
    # Operators can ask for fewer independent changes. The deterministic
    # baseline honors that goal within a narrow safety/cost envelope instead
    # of silently ignoring the UI's priority selector when LLM is disabled.
    eligible = [(i, plan) for i, plan in enumerate(plans)
                if plan["score"] <= plans[0]["score"] + 4
                and plan["disruption_cost"] <= plans[0]["disruption_cost"]]
    prefer_fewer = "fewest" in goal.lower() or "fewer changes" in goal.lower()
    choice = (min(eligible, key=lambda x: (len(x[1]["action_ids"]), x[1]["score"], x[0]))[0]
              if prefer_fewer and eligible else 0)
    deterministic = {"mode":"deterministic_policy","selected_index":choice,
        "explanation":("Fewest changes within four score units of the minimum, without increasing modeled customer disruption."
                       if prefer_fewer else
                       "Lowest combined synthetic impact, execution cost and prior-failure penalty.")}
    if not model_enabled():
        return deterministic
    try:
        # Only give the model admissible plans within four score units of the
        # deterministic optimum. It cannot expand the safety envelope.
        acceptable = [(i,p) for i,p in enumerate(plans) if p["score"]<=plans[0]["score"]+4]
        choices = [{"index":i,"actions":p["actions"],"score":p["score"],
                    "disruption_cost":p["disruption_cost"],"memory_penalty":p["memory_penalty"]}
                   for i,p in acceptable[:6]]
        c=make_client()
        r=c.chat.completions.create(
            model=os.getenv("MAELIN_LLM_MODEL","gpt-4o-mini"),
            messages=[
                {"role":"system","content":"You are an incident-response planning agent. Select ONLY a numbered admissible intervention plan. The graph-based safety kernel already checked reachability. Prefer cheaper and fewer irreversible changes. Do not assert confirmed exploitation or claim real-world safety. You do not execute anything."},
                {"role":"user","content":"Operator goal: "+goal+"\nVerified bounded counterfactual options: "+json.dumps(choices)}],
            tools=[{"type":"function","function":{"name":"select_counterfactual_plan",
                "description":"Select one of the approved safe plans using the operator goal and recorded memory.",
                "parameters":{"type":"object","properties":{
                    "index":{"type":"integer"},"reason":{"type":"string"}},
                    "required":["index","reason"],"additionalProperties":False}}}],
            tool_choice={"type":"function","function":{"name":"select_counterfactual_plan"}},
            temperature=0)
        calls=r.choices[0].message.tool_calls or []
        if len(calls)!=1 or calls[0].function.name!="select_counterfactual_plan":
            raise ValueError("LLM did not select a bounded tool")
        args=json.loads(calls[0].function.arguments)
        chosen=int(args["index"])
        if chosen not in {i for i,_ in acceptable[:6]}:
            raise ValueError("LLM proposed a plan outside the approved safety envelope")
        return {"mode":"llm_tool_choice_validated","selected_index":chosen,
                "explanation":str(args.get("reason", ""))[:400]}
    except Exception as exc:
        return {"mode":"llm_unavailable_policy_fallback","selected_index":deterministic["selected_index"],
                "explanation":f"Model step unavailable ({type(exc).__name__}); safe deterministic policy used."}
