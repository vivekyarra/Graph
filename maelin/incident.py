"""Incident selection is validated against live FalkorDB topology, not JSON traversal."""
from .seed import dataset


def select_scene(store, tenant, source=None, vulnerable=None, target=None, alert=None):
    demo = dataset()
    # Defaults are loaded from this tenant's FalkorDB graph metadata for uploaded scenarios.
    configured = store.graph_scene(tenant) if hasattr(store, 'graph_scene') else demo
    source = source or configured["source"]
    vulnerable = vulnerable or configured["vulnerable"]
    target = target or configured["target"]
    topology = store.topology(tenant)
    kinds = {item["id"]: item["kind"] for item in topology["nodes"]}
    chosen = (source, vulnerable, target)
    if any(node not in kinds for node in chosen):
        raise ValueError("Select source, suspected pivot and target from the current tenant graph")
    if source == target:
        raise ValueError("Source and target must be different")
    if any(kinds[node] == "business_flow" for node in chosen):
        raise ValueError("Select infrastructure assets, not business-flow nodes, for attack traversal")
    is_demo = chosen == (configured["source"], configured["vulnerable"], configured["target"])
    semantic_key = "|".join(kinds[item] for item in chosen)
    return {
        "source":source, "vulnerable":vulnerable, "target":target,
        "fingerprint": configured["fingerprint"] if is_demo else "pivot:%s:%s:%s" % chosen,
        "scenario": configured["scenario"] if is_demo else "Investigation: %s via %s to %s" % chosen,
        "alert": alert or "", "semantic_key": semantic_key,
    }
