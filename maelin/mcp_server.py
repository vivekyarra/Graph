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


@mcp.tool()
def compute_asset_centrality(tenant: str = "alpha") -> dict:
    """Compute PageRank centrality scores for infrastructure assets using FalkorDB algo.pageRank."""
    return {"centrality": store().compute_asset_centrality(tenant)}


@mcp.tool()
def get_team_ownership(tenant: str = "alpha", asset_id: str = "") -> dict:
    """Retrieve organizational ownership subgraph mapping teams to assets and services."""
    return {"ownership": store().team_ownership(tenant, asset_id or None)}


@mcp.tool()
def compute_min_cut(tenant: str = "alpha", vulnerable: str = "auth-service",
                    target: str = "customer-db") -> dict:
    """Minimum pivot cut between a compromised asset and a target via FalkorDB algo.maxFlow."""
    return store().min_cut(tenant, vulnerable, target)


@mcp.tool()
def find_attack_chokepoints(tenant: str = "alpha", source: str = "", target: str = "") -> dict:
    """Rank assets by share of entry->target attack routes through them, plus algo.betweenness."""
    return {"chokepoints": store().chokepoints(tenant, source or None, target or None)}


@mcp.tool()
def ask_company_brain(tenant: str = "alpha", question: str = "Who owns auth-service?") -> dict:
    """Answer with sources: full-text index over documents plus ownership/decision traversal."""
    from .brain import ask
    return ask(store(), tenant, question[:300])


@mcp.tool()
def get_asset_context(tenant: str = "alpha", asset_id: str = "auth-service") -> dict:
    """Owners, on-call people, documents, decisions and customer blast radius for one asset."""
    from .brain import asset_context
    return asset_context(store(), tenant, asset_id)


if __name__ == "__main__":
    mcp.run()
