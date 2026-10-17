"""Test-only Python traversal oracle. Not used by the production service."""

def traversal_fixture(dataset, *, depth=7):
    """ONLY for offline unit tests, never used by the production API."""
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
                dfs(e["to"], nodes + [e["to"]], eid + [e["id"]])
    dfs(src, [src], [])
    paths = []
    depend = {}
    values = {a["id"]:a.get("value",0) for a in dataset["assets"]}
    for e in dataset["depends_edges"]:
        depend.setdefault(e["from"], []).append(e["to"])
    def walk(node, nodes, start):
        if len(nodes) >= 8:
            return
        if len(nodes) > 1:
            paths.append({"flow":start,"value":values[start],"nodes":nodes})
        for nxt in depend.get(node,[]):
            if nxt not in nodes:
                walk(nxt, nodes+[nxt],start)
    for asset in dataset["assets"]:
        if asset["kind"] == "business_flow":
            walk(asset["id"],[asset["id"]],asset["id"])
    return found, paths
