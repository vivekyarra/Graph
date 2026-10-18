"""Read-only counterfactual web API, with operator-reported outcome memory."""
import os
import hmac
from fastapi import Request
from functools import lru_cache
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .store import Store
from .seed import dataset
from .incident import select_scene
from .schema import validate_dataset
from contextlib import asynccontextmanager
from .agents import investigate
from .simulator import run_simulation


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the persistent MCP graph-tool server in the background."""
    if os.getenv("MAELIN_AGENT_TOOLS", "direct") == "mcp":
        import threading
        from .mcp_client import _SESSION
        def warm():
            try:
                _SESSION.ensure()
            except Exception:
                pass  # The first investigation retries and reports the failure.
        threading.Thread(target=warm, daemon=True).start()
    yield


api = FastAPI(title="MAELIN | Graph-native Incident Time Machine", version="0.1.0", lifespan=lifespan)
STATIC = Path(__file__).resolve().parent.parent / "static"
api.mount("/assets", StaticFiles(directory=STATIC), name="assets")


@lru_cache(maxsize=1)
def store():
    return Store(os.getenv("FALKOR_HOST","localhost"),
                 int(os.getenv("FALKOR_PORT","6379")),os.getenv("FALKOR_PASSWORD"))


class Investigation(BaseModel):
    goal: str = Field(default="Minimize customer disruption and remediation cost",max_length=240)
    tenant: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$", default="alpha")
    source: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_-]{0,79}$")
    vulnerable: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_-]{0,79}$")
    target: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_-]{0,79}$")
    alert: str | None = Field(default=None, max_length=400)
    scenario_name: str | None = Field(default=None, max_length=120)


class ScenarioUpload(BaseModel):
    tenant: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")
    dataset: dict


class Simulation(BaseModel):
    tenant: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$", default="alpha")
    session_id: str
    action_ids: list[str] = Field(min_length=1, max_length=3)


class Outcome(BaseModel):
    tenant: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$", default="alpha")
    session_id: str
    action_id: str
    outcome: str
    cost_observed: int = Field(default=0,ge=0,le=1000)
    note: str = Field(default="Synthetic operator-reported incident",max_length=400)
    # Optional operator-supplied resolution time; derived from graph session
    # age when omitted, never invented.
    mttr_seconds: int | None = Field(default=None, ge=0, le=86_400)


class DemoReset(BaseModel):
    tenant: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$", default="alpha")



DEMO_TENANTS = {"alpha", "beta"}


def require_operator(request: Request, tenant: str | None = None):
    """Fail closed for graph reads and writes unless explicitly authorized.

    * MAELIN_OPERATOR_TOKEN set: the header must match it (constant time).
    * MAELIN_PUBLIC_DEMO=1: tokenless access, but only to the synthetic demo
      tenants, so a hosted public demo can never touch other tenants.
    * MAELIN_LOCAL_DEMO=1: loopback-only Docker Compose, never the Internet.
    """
    configured = os.getenv("MAELIN_OPERATOR_TOKEN", "")
    supplied = request.headers.get("x-maelin-operator-token", "")
    if configured and supplied and hmac.compare_digest(configured.encode(), supplied.encode()):
        return
    if os.getenv("MAELIN_PUBLIC_DEMO") == "1" and (tenant or "alpha") in DEMO_TENANTS:
        return
    if configured:
        raise HTTPException(403, "Operator authorization required")
    if os.getenv("MAELIN_LOCAL_DEMO") == "1":
        return
    raise HTTPException(403, "Graph access disabled: configure MAELIN_OPERATOR_TOKEN")


@api.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@api.get("/api/health")
def health(tenant: str = Query("alpha",pattern=r"^[a-z][a-z0-9_-]{0,31}$")):
    try:
        return {"graph_required":True,"seeded":store().ready(tenant),"tenant":tenant}
    except Exception as e:
        raise HTTPException(503,"FalkorDB unreachable. This app has no non-graph fallback.") from e


@api.get("/api/graph")
def graph(request: Request, tenant: str = Query("alpha",pattern=r"^[a-z][a-z0-9_-]{0,31}$")):
    # Namespace isolation is not access control. Protect incident topologies
    # in remote mode using the same operator boundary as graph writes.
    require_operator(request, tenant)
    try:
        return store().topology(tenant)
    except Exception as e:
        raise HTTPException(503,"Could not query FalkorDB topology") from e


@api.get("/api/scene")
def scene_defaults(request: Request, tenant: str = Query("alpha",pattern=r"^[a-z][a-z0-9_-]{0,31}$")):
    require_operator(request, tenant)
    try:
        return store().graph_scene(tenant)
    except Exception as exc:
        raise HTTPException(503,"Could not read FalkorDB incident defaults") from exc


@api.post("/api/scenarios", status_code=201)
def upload_scenario(req: ScenarioUpload, request: Request):
    # Uploads create new tenants, so the public demo allowance never applies.
    require_operator(request, "__upload__")
    try:
        data = validate_dataset(req.dataset)
        # Never overwrite an existing tenant. All topology remains in FalkorDB.
        store().seed(req.tenant, data, reset=False)
        return {"tenant":req.tenant, "nodes":len(data["assets"]),
                "pivot_edges":len(data["pivot_edges"]), "status":"seeded_in_falkordb"}
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, f"Scenario upload failed: {type(exc).__name__}") from exc


@api.post("/api/investigate")
def run(req: Investigation, request: Request):
    require_operator(request, req.tenant)
    try:
        graph_store = store()
        scene = select_scene(graph_store, req.tenant, req.source, req.vulnerable, req.target, req.alert)
        if req.scenario_name:
            scene["scenario"]=req.scenario_name
        return investigate(graph_store,req.tenant,scene,req.goal)
    except LookupError as e:
        raise HTTPException(409,str(e)) from e
    except (OverflowError, ValueError) as e:
        raise HTTPException(422,str(e)) from e
    except Exception as e:
        # No silent memory/graph fallback, no hallucinated success.
        raise HTTPException(503,f"Graph reasoning unavailable: {type(e).__name__}") from e


@api.post("/api/demo/simulate")
def simulate(req: Simulation, request: Request):
    require_operator(request, req.tenant)
    # This clones and MUTATES a graph, never any real infrastructure.
    if os.getenv("MAELIN_ENABLE_DEMO_MUTATIONS", "1") != "1":
        raise HTTPException(403,"Simulation disabled; trusted demo mode only")
    try:
        graph_store = store()
        scene = graph_store.session_scene(req.tenant, req.session_id)
        return run_simulation(graph_store,req.tenant,req.session_id,scene,req.action_ids)
    except PermissionError as e:
        raise HTTPException(403,str(e)) from e
    except (ValueError,LookupError) as e:
        raise HTTPException(422,str(e)) from e
    except OverflowError as e:
        raise HTTPException(422,str(e)) from e
    except Exception as e:
        raise HTTPException(503,f"FalkorDB simulation failed: {type(e).__name__}") from e


@api.post("/api/outcome")
def outcome(req: Outcome, request: Request):
    require_operator(request, req.tenant)
    if req.outcome not in {"unexpected_outage","safe"}:
        raise HTTPException(422,"outcome must be 'unexpected_outage' or 'safe'")
    try:
        allowed=store().session_actions(req.tenant,req.session_id)
        if req.action_id not in allowed:
            raise HTTPException(403,"This action was not proposed in the named session/tenant")
        scene = store().session_scene(req.tenant,req.session_id)
        ep=store().record_outcome(req.tenant,req.session_id,scene["fingerprint"],
                                  req.action_id,req.outcome,req.cost_observed,req.note,
                                  semantic_key=scene.get("semantic_key"),
                                  mttr_seconds=req.mttr_seconds)
        action = next((a for a in store().interventions(req.tenant) if a["id"] == req.action_id), None)
        postmortem = None
        if action is not None:
            from .brain import write_postmortem
            postmortem = write_postmortem(store(), req.tenant, action, req.outcome, req.note,
                                          ep, req.cost_observed)
        return {"episode_id":ep,"evidence_status":"operator_report","postmortem_id":postmortem,
                "note":"Future sessions consult this graph-backed reported outcome."}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(409,str(e)) from e
    except Exception as e:
        raise HTTPException(503,"Could not persist the outcome in FalkorDB") from e


@api.get("/api/trace/{session_id}")
def trace(session_id:str, request: Request, tenant: str = Query("alpha",pattern=r"^[a-z][a-z0-9_-]{0,31}$")):
    require_operator(request, tenant)
    try:
        return {"handoffs":store().history(tenant,session_id)}
    except Exception as e:
        raise HTTPException(503,"Could not retrieve durable handoffs") from e


@api.get("/api/conversation/{session_id}")
def conversation(session_id: str, request: Request,
                 tenant: str = Query("alpha",pattern=r"^[a-z][a-z0-9_-]{0,31}$")):
    require_operator(request, tenant)
    try:
        return {"turns":store().conversation(tenant,session_id)}
    except Exception as exc:
        raise HTTPException(503,"Could not query FalkorDB conversation history") from exc


@api.post("/api/demo/inject-shadow-route")
def inject_shadow_route(req: Investigation, request: Request):
    require_operator(request, req.tenant)
    # Explicit local-demo opt-in, off by default in public deployments.
    if os.getenv("MAELIN_ENABLE_DEMO_MUTATIONS", "1") != "1":
        raise HTTPException(403, "Synthetic injection disabled; set MAELIN_ENABLE_DEMO_MUTATIONS=1 only on a trusted demo instance")
    try:
        return store().inject_shadow_route(req.tenant)
    except LookupError as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(503, "Could not inject synthetic route in FalkorDB") from e


@api.post("/api/demo/reset")
def reset_demo_state(req: DemoReset, request: Request):
    require_operator(request, req.tenant)
    if os.getenv("MAELIN_ENABLE_DEMO_MUTATIONS", "1") != "1":
        raise HTTPException(403, "Demo reset disabled; trusted demo mode only")
    try:
        from .seed import seed_tenant, dataset
        seed_tenant(tenant=req.tenant, reset=True, store=store())
        data = dataset()
        return {
            "status": "reset_successful",
            "tenant": req.tenant,
            "message": f"Successfully re-seeded demo state for tenant {req.tenant!r}",
            "nodes": len(data.get("assets", [])),
            "pivot_edges": len(data.get("pivot_edges", [])),
            "depends_edges": len(data.get("depends_edges", []))
        }
    except Exception as e:
        raise HTTPException(503, f"Could not reset demo state: {type(e).__name__}") from e


@api.get("/api/centrality")
def asset_centrality(request: Request, tenant: str = Query("alpha", pattern=r"^[a-z][a-z0-9_-]{0,31}$")):
    require_operator(request, tenant)
    try:
        return {"centrality": store().compute_asset_centrality(tenant)}
    except Exception as e:
        raise HTTPException(503, f"FalkorDB centrality algorithm failed: {type(e).__name__}") from e


@api.get("/api/teams")
def team_ownership(request: Request, tenant: str = Query("alpha", pattern=r"^[a-z][a-z0-9_-]{0,31}$"),
                   asset_id: str | None = None):
    require_operator(request, tenant)
    try:
        return {"ownership": store().team_ownership(tenant, asset_id)}
    except Exception as e:
        raise HTTPException(503, f"Could not query team ownership: {type(e).__name__}") from e



TENANT_Q = Query("alpha", pattern=r"^[a-z][a-z0-9_-]{0,31}$")
ASSET_ID = r"^[a-z0-9][a-z0-9_-]{0,79}$"


@api.get("/api/intel")
def graph_intel(request: Request, tenant: str = TENANT_Q,
                vulnerable: str | None = Query(None, pattern=ASSET_ID),
                target: str | None = Query(None, pattern=ASSET_ID)):
    """Native FalkorDB algorithms: maxFlow min-cut, betweenness, pageRank."""
    require_operator(request, tenant)
    try:
        s = store()
        scene = s.graph_scene(tenant)
        v, t = vulnerable or scene["vulnerable"], target or scene["target"]
        return {"vulnerable": v, "target": t, "min_cut": s.min_cut(tenant, v, t),
                "chokepoints": s.chokepoints(tenant),
                "centrality": s.compute_asset_centrality(tenant)[:5]}
    except Exception as e:
        raise HTTPException(503, f"FalkorDB algorithm call failed: {type(e).__name__}") from e


@api.get("/api/chokepoints")
def critical_chokepoints(request: Request, tenant: str = TENANT_Q,
                         vulnerable: str | None = Query(None, pattern=ASSET_ID),
                         source: str | None = Query(None, pattern=ASSET_ID),
                         target: str | None = Query(None, pattern=ASSET_ID)):
    """Betweenness ranking plus attack-path cut simulation (read-only)."""
    require_operator(request, tenant)
    try:
        return store().critical_chokepoints(tenant, vulnerable, source, target)
    except OverflowError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:
        raise HTTPException(503, f"FalkorDB chokepoint analysis failed: {type(e).__name__}") from e


@api.get("/api/playbooks")
def proven_playbooks(request: Request, tenant: str = TENANT_Q,
                     cve_id: str | None = Query(None, max_length=180),
                     service_tier: str = Query("service", max_length=40)):
    """Cross-session memory: playbooks ranked by usage and observed MTTR."""
    require_operator(request, tenant)
    try:
        fingerprint = cve_id or store().graph_scene(tenant).get("fingerprint", "")
        return {"playbooks": store().recall_proven_playbook(tenant, fingerprint, service_tier)}
    except Exception as e:
        raise HTTPException(503, f"FalkorDB playbook recall failed: {type(e).__name__}") from e


@api.get("/api/stats")
def graph_stats(request: Request, tenant: str = TENANT_Q):
    require_operator(request, tenant)
    try:
        return store().stats(tenant)
    except Exception as e:
        raise HTTPException(503, "Could not read FalkorDB statistics") from e


class BrainQuestion(BaseModel):
    tenant: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$", default="alpha")
    question: str = Field(min_length=2, max_length=300)


@api.post("/api/brain/ask")
def brain_ask(req: BrainQuestion, request: Request):
    require_operator(request, req.tenant)
    try:
        from .brain import ask
        return ask(store(), req.tenant, req.question)
    except Exception as e:
        raise HTTPException(503, f"Company Brain query failed: {type(e).__name__}") from e


@api.get("/api/brain/asset/{asset_id}")
def brain_asset(asset_id: str, request: Request, tenant: str = TENANT_Q):
    require_operator(request, tenant)
    import re as _re
    if not _re.fullmatch(ASSET_ID, asset_id):
        raise HTTPException(422, "Invalid asset id")
    try:
        from .brain import asset_context
        return asset_context(store(), tenant, asset_id)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(503, f"Company Brain query failed: {type(e).__name__}") from e
