"""Strict untrusted synthetic graph upload validation.

Uploads create new FalkorDB tenant graphs; there is no JSON/in-memory
production traversal and no overwrite of an existing tenant.
"""
import math
from copy import deepcopy
from .logic import MAX_CANDIDATE_ACTIONS

KINDS = {"ingress", "service", "identity", "database", "business_flow"}
MAX_NODES = 120
MAX_EDGES = 240


def _identifier(value):
    return isinstance(value, str) and 1 <= len(value) <= 80 and all(
        c.isalnum() or c in "-_" for c in value) and value.isascii()


def _number(value, max_value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= max_value


def validate_dataset(payload):
    """Return normalized, bounded JSON-compatible seed data or raise ValueError."""
    if not isinstance(payload, dict):
        raise ValueError("Graph payload must be an object")
    data = deepcopy(payload)
    assets, pivots, dependencies, actions = (
        data.get("assets"), data.get("pivot_edges"), data.get("depends_edges"), data.get("actions"))
    if not isinstance(assets, list) or not 3 <= len(assets) <= MAX_NODES:
        raise ValueError("Provide 3–120 assets")
    if not all(isinstance(x, dict) for x in assets):
        raise ValueError("Assets must be objects")
    ids = [x.get("id") for x in assets]
    if not all(_identifier(x) for x in ids) or len(set(ids)) != len(ids):
        raise ValueError("Asset IDs must be unique ASCII identifiers")
    for index, asset in enumerate(assets):
        if asset.get("kind") not in KINDS:
            raise ValueError("Unknown asset kind")
        if not _number(asset.get("value", 0), 100000):
            raise ValueError("Invalid business impact value")
        angle = 2 * math.pi * index / len(assets)
        asset["x"] = asset.get("x", round(410 + 270 * math.cos(angle), 2))
        asset["y"] = asset.get("y", round(245 + 180 * math.sin(angle), 2))
        if not _number(asset["x"], 10000) or not _number(asset["y"], 10000):
            raise ValueError("Invalid asset position")
        asset["critical"] = asset.get("critical", False)
        if type(asset["critical"]) is not bool:
            raise ValueError("Asset critical must be a boolean")
        asset.setdefault("value", 0)
    if not all(isinstance(seq, list) for seq in (pivots, dependencies, actions)):
        raise ValueError("Edges and actions must be arrays")
    if len(pivots) + len(dependencies) > MAX_EDGES:
        raise ValueError("Graph exceeds 240 edges")
    if not 1 <= len(actions) <= MAX_CANDIDATE_ACTIONS:
        raise ValueError("Require 1–48 interventions")
    edge_ids = set()
    for edge in pivots + dependencies:
        if not isinstance(edge, dict) or not _identifier(edge.get("id")):
            raise ValueError("Invalid relationship ID")
        if edge["id"] in edge_ids or edge.get("from") not in ids or edge.get("to") not in ids:
            raise ValueError("Duplicate relationship or unknown endpoint")
        edge_ids.add(edge["id"])
        if edge.get("from") == edge.get("to"):
            raise ValueError("Self-referential graph edges are unsupported")
        note = edge.get("evidence", "Synthetic graph relationship")
        if not isinstance(note, str) or len(note) > 400:
            raise ValueError("Invalid graph evidence text")
        edge["evidence"] = note
    action_ids = set()
    piv_ids = {edge["id"] for edge in pivots}
    for action in actions:
        if not isinstance(action, dict) or not _identifier(action.get("id")) or action["id"] in action_ids:
            raise ValueError("Intervention identifiers must be unique")
        action_ids.add(action["id"])
        if not isinstance(action.get("label"), str) or not 1 <= len(action["label"]) <= 160:
            raise ValueError("Invalid intervention label")
        if not _number(action.get("cost"), 100000):
            raise ValueError("Intervention cost must be finite and nonnegative")
        for field, allowed in (("blocked_nodes", set(ids)), ("blocked_edges", piv_ids)):
            value = action.get(field, [])
            if not isinstance(value, list) or any(x not in allowed for x in value):
                raise ValueError("Intervention references unknown assets or pivot edges")
            action[field] = value
        if not action["blocked_nodes"] and not action["blocked_edges"]:
            raise ValueError("Each intervention must block at least one asset or pivot")
        note = action.get("note", "")
        if not isinstance(note, str) or len(note) > 400:
            raise ValueError("Invalid intervention note")
        action["note"] = note
    for field in ("source", "vulnerable", "target"):
        if data.get(field) not in ids or next(a for a in assets if a["id"] == data[field])["kind"] == "business_flow":
            raise ValueError("A source, compromised node and target must identify infrastructure assets")
    if data["source"] == data["target"]:
        raise ValueError("Source and target cannot match")
    for field in ("scenario", "fingerprint"):
        if not isinstance(data.get(field), str) or not 1 <= len(data[field]) <= 180:
            raise ValueError("Scenario and fingerprint must be nonempty and at most 180 characters")
    return data
