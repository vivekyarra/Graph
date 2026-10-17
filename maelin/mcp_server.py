"""Optional MCP bridge. Install pip install -e '.[mcp]' and run module.

No arbitrary Cypher. A caller can only invoke typed, bounded tools.
"""
import os
from mcp.server.fastmcp import FastMCP
from .api import store
from .seed import dataset
from .agents import investigate

mcp = FastMCP("MAELIN Graph Reasoning")


@mcp.tool()
def inspect_attack_paths(
    tenant: str = "alpha",
    source: str | None = None,
    vulnerable: str | None = None,
    target: str | None = None,
) -> dict:
    """Bounded attack paths through the specific compromised service."""
    d = dataset()
    src = source or d["source"]
    vuln = vulnerable or d["vulnerable"]
    tgt = target or d["target"]
    return {
        "paths": store().attack_paths(tenant, src, vuln, tgt),
        "source": src,
        "vulnerable": vuln,
        "target": tgt,
        "limit": "7 hops, up to 256 matching paths",
    }


@mcp.tool()
def inspect_business_dependencies(tenant: str = "alpha") -> dict:
    """Graph-proven dependent customer flows with declared synthetic values."""
    return {"dependency_paths": store().business_paths(tenant)}


@mcp.tool()
def recall_incident_outcomes(tenant: str = "alpha", fingerprint: str | None = None, component: str | None = None) -> dict:
    """Tenant-isolated memory graph query, including associative recall and evidence status."""
    d = dataset()
    fp = fingerprint or d["fingerprint"]
    return {"precedents": store().recall(tenant, fp, component=component)}


@mcp.tool()
def propose_containment(
    tenant: str = "alpha",
    goal: str = "Minimize customer disruption and remediation cost",
    source: str | None = None,
    vulnerable: str | None = None,
    target: str | None = None,
    scenario_name: str | None = None,
) -> dict:
    """Three-agent safety pipeline. Generates plans only; never changes live systems."""
    d = dataset()
    scene = dict(d)
    if source:
        scene["source"] = source
    if vulnerable:
        scene["vulnerable"] = vulnerable
    if target:
        scene["target"] = target
    if scenario_name:
        scene["scenario"] = scenario_name
    return investigate(store(), tenant, scene, goal)


if __name__=="__main__":
    mcp.run()
