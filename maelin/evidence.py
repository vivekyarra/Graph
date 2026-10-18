"""Deterministic evidence IDs and the anti-hallucination guard.

The guard is pure set membership: every node the remediation agent cites must
have come back from a FalkorDB traversal in this investigation. No model is
asked to grade itself, so the check is reproducible and cheap.
"""
from collections.abc import Mapping

EVIDENCE_PREFIX = "E"
# Only graph-node citations are checked. Business flows are impact labels, not
# nodes on an attack path, so they are deliberately excluded.
_NODE_KEYS = ("blocked_nodes", "cited_nodes", "services", "service",
              "chokepoint_service", "cves", "iam_roles", "roles", "target_roles")


def assign_evidence_ids(records, start=1):
    """Attach ``[E1]``, ``[E2]`` ... in FalkorDB row order (deterministic)."""
    out = []
    for index, record in enumerate(records or [], start=start):
        item = dict(record) if isinstance(record, Mapping) else {"value": record}
        item["evidence_id"] = f"[{EVIDENCE_PREFIX}{index}]"
        out.append(item)
    return out


def traversed_node_ids(paths):
    """Ordered, de-duplicated node IDs from graph-returned path records."""
    ids = {}
    for path in paths or []:
        nodes = path.get("nodes") if isinstance(path, Mapping) else path
        for node in nodes or []:
            ids[str(node)] = None
    return list(ids)


def plan_citations(plan, paths):
    """Node IDs a plan actually touches: blocked assets plus pivot endpoints."""
    if not isinstance(plan, Mapping):
        return []
    cited = {str(n) for n in (plan.get("blocked_nodes") or [])}
    blocked_edges = {str(e) for e in (plan.get("blocked_edges") or [])}
    for path in paths or []:
        if not isinstance(path, Mapping):
            continue
        edges = [str(e) for e in (path.get("edges") or [])]
        nodes = path.get("nodes") or []
        for edge in blocked_edges.intersection(edges):
            index = edges.index(edge)
            if index < len(nodes):
                cited.add(str(nodes[index]))
            if index + 1 < len(nodes):
                cited.add(str(nodes[index + 1]))
    return sorted(cited)


def _walk(value, *, key=None):
    if isinstance(value, Mapping):
        for child_key, child in value.items():
            yield from _walk(child, key=child_key)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            if key in _NODE_KEYS and isinstance(item, str):
                yield item
            else:
                yield from _walk(item, key=key)


def _collect_evidence_ids(value):
    found = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key == "evidence_ids" and isinstance(child, (list, tuple, set)):
                found.extend(str(x) for x in child if x)
            else:
                found.extend(_collect_evidence_ids(child))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.extend(_collect_evidence_ids(item))
    return list(dict.fromkeys(found))


def verify_agent_remediation(agent_response, traversed_node_ids, paths=None):
    """Cross-check every cited service/role/fingerprint against graph evidence.

    Returns the ``hallucination_check`` payload surfaced by the API and the UI
    badge. ``verified`` is true only when at least one citation exists and all
    of them were actually returned by FalkorDB in this investigation.

    ``paths`` is optional; when supplied, blocked *edges* are resolved to the
    node endpoints of those graph-returned paths before checking, so an
    edge-only plan is verified against the real hop it cuts.
    """
    traversed = [str(x) for x in (traversed_node_ids or []) if x is not None]
    traversed = list(dict.fromkeys(traversed))
    known = set(traversed)
    cited = set(_walk(agent_response))
    if paths is not None and isinstance(agent_response, Mapping):
        cited.update(plan_citations(agent_response.get("recommended"), paths))
    cited = sorted(cited)
    unverified = [node for node in cited if node not in known]
    verified_nodes = [node for node in cited if node in known]
    evidence_ids = _collect_evidence_ids(agent_response)
    return {
        "verified": bool(cited) and bool(known) and not unverified,
        "evidence_ids": evidence_ids,
        "verified_nodes": verified_nodes,
        "unverified_nodes": unverified,
        "citations_checked": len(cited),
        "method": "deterministic set membership over FalkorDB-returned node IDs",
        "boundary": "Proves the plan cites only traversed graph nodes; it does not "
                    "prove the modeled topology is complete.",
    }


def severance_sentence(chokepoints):
    """The exact cut-impact sentence used in the remediation summary."""
    if not chokepoints:
        return ""
    top = chokepoints[0]
    service = top.get("service") or top.get("chokepoint_service") or "unknown"
    severed = int(top.get("paths_severed") or 0)
    total = int(top.get("total_paths") or 0)
    pct = top.get("pct_blast_radius_eliminated")
    try:
        pct = float(pct)
    except (TypeError, ValueError):
        pct = (100.0 * severed / total) if total else 0.0
    roles = top.get("target_roles") or []
    role = ", ".join(str(r) for r in roles) if roles else "privileged identities"
    return (f"Isolating `{service}` severs {severed} of {total} "
            f"({pct:.1f}%) active exploit paths to `{role}`.")
