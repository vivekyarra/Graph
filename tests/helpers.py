"""Test-only helpers and offline verification oracles.

Never imported or used by production services.
"""
from __future__ import annotations


def traversal_fallback(dataset, *, depth=7):
    """DFS path finder used ONLY in offline unit tests to verify optimizer behavior without a live database."""
    src, dst, vuln = dataset["source"], dataset["target"], dataset["vulnerable"]
    edges = {}
    for e in dataset["pivot_edges"]:
        edges.setdefault(e["from"], []).append(e)
    found = []

    def dfs(node, nodes, eid):
        if node == dst:
            if vuln in nodes:
                found.append({"nodes": list(nodes), "edges": list(eid)})
            return
        if len(eid) >= depth:
            return
        for e in edges.get(node, []):
            if e["to"] not in nodes:
                nodes.append(e["to"])
                eid.append(e["id"])
                dfs(e["to"], nodes, eid)
                nodes.pop()
                eid.pop()

    dfs(src, [src], [])
    business = []
    b_edges = {}
    for e in dataset["depends_edges"]:
        b_edges.setdefault(e["from"], []).append(e)

    def b_dfs(node, nodes, eid, flow, val):
        business.append({"flow": flow, "value": val, "nodes": list(nodes)})
        if len(eid) >= depth:
            return
        for e in b_edges.get(node, []):
            if e["to"] not in nodes:
                nodes.append(e["to"])
                eid.append(e["id"])
                b_dfs(e["to"], nodes, eid, flow, val)
                nodes.pop()
                eid.pop()

    for a in dataset["assets"]:
        if a["kind"] == "business_flow":
            b_dfs(a["id"], [a["id"]], [], a["id"], a.get("value", 0))

    return found, business
