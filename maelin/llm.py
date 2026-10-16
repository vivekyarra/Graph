"""Optional bounded LLM planning over verified counterfactual alternatives.

Never executes infrastructure commands or writes Cypher. Model output is
untrusted and validated against the deterministic safety kernel.
"""
import json
import os


def adjudicate(plans, goal="minimize customer disruption"):
    if not plans:
        return {"mode":"no_safe_plan","selected_index":None,"explanation":"No fully covering candidate found."}
    deterministic = {"mode":"deterministic_policy","selected_index":0,
        "explanation":"Lowest combined synthetic impact, execution cost and prior-failure penalty."}
    if not os.getenv("OPENAI_API_KEY") or os.getenv("MAELIN_USE_LLM")!="1":
        return deterministic
    try:
        from openai import OpenAI
        # Only give the model admissible plans within four score units of the
        # deterministic optimum. It cannot expand the safety envelope.
        acceptable = [(i,p) for i,p in enumerate(plans) if p["score"]<=plans[0]["score"]+4]
        choices = [{"index":i,"actions":p["actions"],"score":p["score"],
                    "disruption_cost":p["disruption_cost"],"memory_penalty":p["memory_penalty"]}
                   for i,p in acceptable[:6]]
        c=OpenAI(timeout=12.0)
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
        return {"mode":"llm_unavailable_policy_fallback","selected_index":0,
                "explanation":f"Model step unavailable ({type(exc).__name__}); safe deterministic policy used."}
