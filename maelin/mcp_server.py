"""Bounded FalkorDB MCP stdio tools. No arbitrary query or write capability."""
from mcp.server.fastmcp import FastMCP
from .api import store
from .seed import dataset
from .agents import investigate

mcp = FastMCP("MAELIN Graph Reasoning")


@mcp.tool()
def inspect_attack_paths(tenant: str = "alpha", source: str = "internet",
                         vulnerable: str = "auth-service", target: str = "customer-db") -> dict:
    """Enumerate bounded graph-derived paths for a selected incident."""
    return {"paths": store().attack_paths(tenant, source, vulnerable, target)}


@mcp.tool()
def inspect_business_dependencies(tenant: str = "alpha") -> dict:
    """Read Cypher-derived business dependency paths."""
    return {"dependency_paths": store().business_paths(tenant)}


@mcp.tool()
def recall_incident_outcomes(tenant: str = "alpha",
                             fingerprint: str = "exploited-identity-to-customer-db", semantic_key: str = "") -> dict:
    """Read tenant-scoped graph procedural and episodic evidence."""
    return {"precedents": store().recall(tenant, fingerprint, semantic_key or None)}


@mcp.tool()
def list_candidate_interventions(tenant: str = "alpha") -> dict:
    """Read candidate containment interventions from FalkorDB."""
    return {"interventions": store().interventions(tenant)}


@mcp.tool()
def propose_containment(tenant: str = "alpha", source: str | None = None,
                        vulnerable: str | None = None, target: str | None = None,
                        goal: str = "Minimize customer disruption") -> dict:
    """Validated dynamic graph investigation, never real infrastructure changes."""
    from .incident import select_scene
    scene = select_scene(store(), tenant, source, vulnerable, target)
    return investigate(store(), tenant, scene, goal)


if __name__ == "__main__":
    mcp.run()
