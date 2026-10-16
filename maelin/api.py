"""Read-only counterfactual web API, with operator-reported outcome memory."""
import os
import hmac
from fastapi import Request
from functools import lru_cache
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from .store import Store
from .seed import dataset
from .agents import investigate
from .simulator import run_simulation

api = FastAPI(title="MAELIN | Graph-native Incident Time Machine",version="0.1.0")
STATIC = Path(__file__).resolve().parent.parent / "static"


@lru_cache(maxsize=1)
def store():
    return Store(os.getenv("FALKOR_HOST","localhost"),
                 int(os.getenv("FALKOR_PORT","6379")),os.getenv("FALKOR_PASSWORD"))


class Investigation(BaseModel):
    goal: str = Field(default="Minimize customer disruption and remediation cost",max_length=240)
    tenant: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$", default="alpha")


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



def require_operator(request: Request):
    """Fail closed for all graph-writing APIs except explicit local demo mode.

    For remote deployments configure MAELIN_OPERATOR_TOKEN and TLS at a proxy.
    MAELIN_LOCAL_DEMO is for loopback-only Docker Compose, never the Internet.
    """
    configured = os.getenv("MAELIN_OPERATOR_TOKEN", "")
    supplied = request.headers.get("x-maelin-operator-token", "")
    if configured:
        if hmac.compare_digest(configured, supplied):
            return
        raise HTTPException(403, "Operator authorization required")
    if os.getenv("MAELIN_LOCAL_DEMO") == "1":
        return
    raise HTTPException(403, "Graph writes disabled: configure MAELIN_OPERATOR_TOKEN")


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
def graph(tenant: str = Query("alpha",pattern=r"^[a-z][a-z0-9_-]{0,31}$")):
    try:
        return store().topology(tenant)
    except Exception as e:
        raise HTTPException(503,"Could not query FalkorDB topology") from e


@api.post("/api/investigate")
def run(req: Investigation, request: Request):
    require_operator(request)
    try:
        return investigate(store(),req.tenant,dataset(),req.goal)
    except LookupError as e:
        raise HTTPException(409,str(e)) from e
    except OverflowError as e:
        raise HTTPException(422,str(e)) from e
    except Exception as e:
        # No silent memory/graph fallback, no hallucinated success.
        raise HTTPException(503,f"Graph reasoning unavailable: {type(e).__name__}") from e


@api.post("/api/demo/simulate")
def simulate(req: Simulation, request: Request):
    require_operator(request)
    # This clones and MUTATES a graph, never any real infrastructure.
    if os.getenv("MAELIN_ENABLE_DEMO_MUTATIONS") != "1":
        raise HTTPException(403,"Simulation disabled; trusted demo mode only")
    try:
        return run_simulation(store(),req.tenant,req.session_id,dataset(),req.action_ids)
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
    require_operator(request)
    if req.outcome not in {"unexpected_outage","safe"}:
        raise HTTPException(422,"outcome must be 'unexpected_outage' or 'safe'")
    try:
        allowed=store().session_actions(req.tenant,req.session_id)
        if req.action_id not in allowed:
            raise HTTPException(403,"This action was not proposed in the named session/tenant")
        ep=store().record_outcome(req.tenant,req.session_id,dataset()["fingerprint"],
                                  req.action_id,req.outcome,req.cost_observed,req.note)
        return {"episode_id":ep,"evidence_status":"operator_report",
                "note":"Future sessions consult this graph-backed reported outcome."}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(409,str(e)) from e
    except Exception as e:
        raise HTTPException(503,"Could not persist the outcome in FalkorDB") from e


@api.get("/api/trace/{session_id}")
def trace(session_id:str, tenant: str = Query("alpha",pattern=r"^[a-z][a-z0-9_-]{0,31}$")):
    try:
        return {"handoffs":store().history(tenant,session_id)}
    except Exception as e:
        raise HTTPException(503,"Could not retrieve durable handoffs") from e


@api.post("/api/demo/inject-shadow-route")
def inject_shadow_route(req: Investigation, request: Request):
    require_operator(request)
    # Explicit local-demo opt-in, off by default in public deployments.
    if os.getenv("MAELIN_ENABLE_DEMO_MUTATIONS") != "1":
        raise HTTPException(403, "Synthetic injection disabled; set MAELIN_ENABLE_DEMO_MUTATIONS=1 only on a trusted demo instance")
    try:
        return store().inject_shadow_route(req.tenant)
    except LookupError as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(503, "Could not inject synthetic route in FalkorDB") from e
