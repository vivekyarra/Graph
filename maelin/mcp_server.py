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
def inspect_attack_paths(tenant: str = "alpha") -> dict:
    """Bounded attack paths through the specific compromised service."""
    d=dataset()
    return {"paths":store().attack_paths(tenant,d["source"],d["vulnerable"],d["target"]),
            "limit":"7 hops, up to 256 matching paths"}


@mcp.tool()
def inspect_business_dependencies(tenant: str = "alpha") -> dict:
    """Graph-proven dependent customer flows with declared synthetic values."""
    return {"dependency_paths":store().business_paths(tenant)}


@mcp.tool()
def recall_incident_outcomes(tenant: str = "alpha") -> dict:
    """Tenant-isolated memory graph query, including outcome evidence status."""
    return {"precedents":store().recall(tenant,dataset()["fingerprint"])}


@mcp.tool()
def propose_containment(tenant: str = "alpha") -> dict:
    """Three-agent safety pipeline. Generates plans only; never changes live systems."""
    return investigate(store(),tenant,dataset())


if __name__=="__main__":
    mcp.run()
