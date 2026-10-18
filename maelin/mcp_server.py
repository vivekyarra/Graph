"""Bounded FalkorDB MCP stdio tools. No arbitrary query or write capability.

Every tool returns a ``telemetry`` list: one row per FalkorDB query executed for
that call, including the server-reported ``run_time_ms``. The in-process agent
loop merges these rows into the investigation trace.
"""
from mcp.server.fastmcp import FastMCP
from .api import store
from .seed import dataset
from .agents import investigate
from .telemetry import telemetry_scope

mcp = FastMCP("MAELIN Graph Reasoning")


def _traced(action):
    """Run one bounded tool inside a fresh trace and return its telemetry."""
    with telemetry_scope() as trace:
        result = action()
    if isinstance(result, dict):
        result = dict(result)
        # propose_containment already carries its own nested investigation trace.
        existing = result.get("telemetry") if isinstance(result.get("telemetry"), list) else []
        merged = list(existing)
        for row in trace:
            if row not in merged:
                merged.append(row)
        result["telemetry"] = merged
    return result


@mcp.tool()
def inspect_attack_paths(tenant: str = "alpha", source: str = "internet",
                         vulnerable: str = "auth-service", target: str = "customer-db") -> dict:
    """Enumerate bounded graph-derived paths for a selected incident."""
    return _traced(lambda: {"paths": store().attack_paths(tenant, source, vulnerable, target)})


@mcp.tool()
def inspect_business_dependencies(tenant: str = "alpha") -> dict:
    """Read Cypher-derived business dependency paths."""
    return _traced(lambda: {"dependency_paths": store().business_paths(tenant)})


@mcp.tool()
def recall_incident_outcomes(tenant: str = "alpha",
                             fingerprint: str = "exploited-identity-to-customer-db", semantic_key: str = "") -> dict:
    """Read tenant-scoped graph procedural and episodic evidence."""
    return _traced(lambda: {"precedents": store().recall(tenant, fingerprint, semantic_key or None)})


@mcp.tool()
def recall_proven_playbook(tenant: str = "alpha",
                           cve_id: str = "exploited-identity-to-customer-db",
                           service_tier: str = "service") -> dict:
    """Rank reusable playbooks by cross-session usage and observed MTTR."""
    return _traced(lambda: {"playbooks": store().recall_proven_playbook(tenant, cve_id, service_tier)})


@mcp.tool()
def list_candidate_interventions(tenant: str = "alpha") -> dict:
    """Read candidate containment interventions from FalkorDB."""
    return _traced(lambda: {"interventions": store().interventions(tenant)})


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
    return _traced(lambda: {"centrality": store().compute_asset_centrality(tenant)})


@mcp.tool()
def get_team_ownership(tenant: str = "alpha", asset_id: str = "") -> dict:
    """Retrieve organizational ownership subgraph mapping teams to assets and services."""
    return _traced(lambda: {"ownership": store().team_ownership(tenant, asset_id or None)})


@mcp.tool()
def compute_min_cut(tenant: str = "alpha", vulnerable: str = "auth-service",
                    target: str = "customer-db") -> dict:
    """Minimum pivot cut between a compromised asset and a target via FalkorDB algo.maxFlow."""
    return _traced(lambda: store().min_cut(tenant, vulnerable, target))


@mcp.tool()
def find_attack_chokepoints(tenant: str = "alpha", source: str = "", target: str = "") -> dict:
    """Rank assets by share of entry->target attack routes through them, plus algo.betweenness."""
    return _traced(lambda: {"chokepoints": store().chokepoints(tenant, source or None, target or None)})


@mcp.tool()
def find_critical_chokepoints(tenant: str = "alpha", vulnerable: str = "",
                              source: str = "", target: str = "", limit: int = 5) -> dict:
    """Native betweenness plus attack-path cut simulation on the live topology graph.

    Returns how many distinct ingress->service->privileged-identity exploit
    paths isolating each service would sever, with the percentage of the
    modeled blast radius eliminated.
    """
    return _traced(lambda: store().critical_chokepoints(
        tenant, vulnerable or None, source or None, target or None,
        max(1, min(int(limit), 25))))


@mcp.tool()
def ask_company_brain(tenant: str = "alpha", question: str = "Who owns auth-service?") -> dict:
    """Answer with sources: full-text index over documents plus ownership/decision traversal."""
    from .brain import ask
    return _traced(lambda: ask(store(), tenant, question[:300]))


@mcp.tool()
def get_asset_context(tenant: str = "alpha", asset_id: str = "auth-service") -> dict:
    """Owners, on-call people, documents, decisions and customer blast radius for one asset."""
    from .brain import asset_context
    return _traced(lambda: asset_context(store(), tenant, asset_id))


if __name__ == "__main__":
    mcp.run()
