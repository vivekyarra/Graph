"""Company Brain: people, teams, documents and decisions in the same FalkorDB
graph as the infrastructure they describe.

Answers come from a full-text index hit followed by graph traversal
(Document -> Asset -> Team -> Person, Decision -> source Document), so every
sentence in an answer cites the node it came from. No LLM is required; when one
is configured it may only rephrase the cited facts.
"""
from __future__ import annotations
import hashlib
import re

STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "who", "what", "why", "how", "when", "which",
    "do", "does", "did", "to", "of", "for", "on", "in", "and", "or", "we", "our", "it",
    "should", "can", "i", "me", "my", "about", "with", "this", "that", "be", "if", "owns",
    "own", "know", "knows", "tell",
}


def search_terms(question: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", (question or "").lower())
    return [w for w in dict.fromkeys(words) if len(w) > 1 and w not in STOPWORDS][:8]


def _fulltext(graph, terms, limit=6):
    if not terms:
        return []
    # RediSearch syntax: alternatives with '|', prefix match with '*'.
    query = "|".join(f"{t}*" if len(t) > 3 else t for t in terms)
    rows = graph.ro_query("""CALL db.idx.fulltext.queryNodes('Document', $q) YIELD node, score
RETURN node.id, node.kind, node.title, node.body, node.created, score
ORDER BY score DESC LIMIT $limit""", {"q": query, "limit": limit}).result_set
    return [{"id": r[0], "kind": r[1], "title": r[2], "body": r[3], "created": r[4],
             "score": round(float(r[5]), 3)} for r in rows]


def _asset_hits(graph, terms):
    if not terms:
        return []
    rows = graph.ro_query("""MATCH (a:Asset)
WITH a, [t IN $terms WHERE toLower(a.id) CONTAINS t OR toLower(coalesce(a.role,'')) CONTAINS t] AS hit
WHERE size(hit) > 0 RETURN a.id ORDER BY size(hit) DESC, a.id LIMIT 4""", {"terms": terms}).result_set
    return [r[0] for r in rows]


def asset_context(store, tenant, asset_id):
    """Everything the company knows about one asset, with provenance."""
    from .evidence import assign_evidence_ids
    g, _ = store.graphs(tenant)
    exists = g.ro_query("MATCH (a:Asset {id:$id}) RETURN a.kind, a.role", {"id": asset_id}).result_set
    if not exists:
        raise LookupError("Unknown asset")
    owners = g.ro_query("""MATCH (t:Team)-[:OWNS]->(:Asset {id:$id})
OPTIONAL MATCH (p:Person)-[:MEMBER_OF]->(t)
RETURN t.id, t.name, t.lead, t.contact,
       collect(CASE WHEN p IS NULL THEN NULL ELSE {id:p.id, name:p.name, title:p.title, on_call:p.on_call} END)""",
                        {"id": asset_id}).result_set
    docs = g.ro_query("""MATCH (d:Document)-[:ABOUT]->(:Asset {id:$id})
OPTIONAL MATCH (d)-[:AUTHORED_BY]->(p:Person)
RETURN d.id, d.kind, d.title, d.created, p.name, d.origin ORDER BY d.created DESC""",
                      {"id": asset_id}).result_set
    decisions = g.ro_query("""MATCH (d:Decision)-[:AFFECTS]->(:Asset {id:$id})
MATCH (d)-[:DECIDED_BY]->(p:Person), (d)-[:SOURCED_FROM]->(src:Document)
RETURN d.id, d.title, d.rationale, p.name, src.id, src.title ORDER BY d.created DESC""",
                           {"id": asset_id}).result_set
    return {
        "asset_id": asset_id, "kind": exists[0][0], "role": exists[0][1],
        "owners": [{"team_id": r[0], "team": r[1], "lead": r[2], "contact": r[3],
                    "people": [p for p in r[4] if p]} for r in owners],
        "documents": assign_evidence_ids([{"id": r[0], "kind": r[1], "title": r[2], "created": r[3],
                       "author": r[4], "origin": r[5]} for r in docs]),
        "decisions": assign_evidence_ids([{"id": r[0], "title": r[1], "rationale": r[2], "decided_by": r[3],
                       "source_id": r[4], "source_title": r[5]} for r in decisions]),
        "blast_radius": store.blast_radius(tenant, asset_id),
    }


def ask(store, tenant, question):
    """Answer an operational question with graph-sourced citations."""
    g, _ = store.graphs(tenant)
    terms = search_terms(question)
    docs = _fulltext(g, terms)
    assets = _asset_hits(g, terms)
    doc_ids = [d["id"] for d in docs]
    linked = g.ro_query("""MATCH (d:Document)-[:ABOUT]->(a:Asset) WHERE d.id IN $ids
RETURN d.id, collect(a.id)""", {"ids": doc_ids}).result_set if doc_ids else []
    about = {r[0]: r[1] for r in linked}
    focus = list(dict.fromkeys(assets + [a for d in docs[:2] for a in about.get(d["id"], [])]))[:3]
    owners = g.ro_query("""MATCH (t:Team)-[:OWNS]->(a:Asset) WHERE a.id IN $ids
OPTIONAL MATCH (p:Person {on_call:true})-[:MEMBER_OF]->(t)
RETURN a.id, t.name, t.lead, collect(p.name)""", {"ids": focus}).result_set if focus else []
    decisions = g.ro_query("""MATCH (d:Decision)-[:SOURCED_FROM]->(src:Document)
OPTIONAL MATCH (d)-[:AFFECTS]->(a:Asset)
WITH d, src, collect(a.id) AS assets
WHERE src.id IN $docs OR any(x IN assets WHERE x IN $focus)
MATCH (d)-[:DECIDED_BY]->(p:Person)
RETURN d.id, d.title, p.name, src.id, src.title ORDER BY d.created DESC LIMIT 3""",
                           {"docs": doc_ids, "focus": focus}).result_set

    sources, lines = [], []
    if docs:
        top = docs[0]
        lines.append(f"{top['title']}: {top['body'].split('. ')[0].rstrip('.')}.")
        for d in docs[:4]:
            sources.append({"type": "document", "id": d["id"], "kind": d["kind"],
                            "title": d["title"], "score": d["score"]})
    for r in owners:
        on_call = ", ".join(n for n in r[3] if n) or "no one listed"
        lines.append(f"{r[0]} is owned by {r[1]} (lead {r[2]}; on call: {on_call}).")
        sources.append({"type": "ownership", "id": r[0], "title": f"{r[1]} owns {r[0]}"})
    for r in decisions:
        lines.append(f"Decision by {r[2]}: {r[1]} (source: {r[4]}).")
        sources.append({"type": "decision", "id": r[0], "title": r[1], "source_id": r[3]})
    if not lines:
        lines.append("Nothing in the company graph matches that question yet.")
    return {"question": question, "terms": terms, "answer": " ".join(lines),
            "focus_assets": focus, "sources": sources,
            "method": "db.idx.fulltext.queryNodes + Cypher traversal (Document→Asset→Team→Person, Decision→Document)"}


def write_postmortem(store, tenant, action, outcome, note, episode_id, cost):
    """Keep the brain current: every operator report becomes a cited document."""
    g, _ = store.graphs(tenant)
    doc_id = "pm-auto-" + hashlib.sha1(episode_id.encode()).hexdigest()[:10]
    if g.ro_query("MATCH (d:Document {id:$id}) RETURN d.id", {"id": doc_id}).result_set:
        return doc_id
    endpoints = g.ro_query("""MATCH (a:Asset)-[r:CAN_PIVOT]->(b:Asset) WHERE r.edge_id IN $edges
RETURN collect(DISTINCT a.id) + collect(DISTINCT b.id)""",
                           {"edges": action.get("blocked_edges", [])}).result_set
    about = sorted(set(action.get("blocked_nodes", [])) | set(endpoints[0][0] if endpoints else []))
    verdict = "caused an unexpected outage" if outcome == "unexpected_outage" else "was reported safe"
    from .store import iso_now
    store._create_document(g, {
        "id": doc_id, "kind": "postmortem", "origin": "operator_report", "episode_id": episode_id,
        "title": f"{action['label']} {verdict}",
        "body": (f"Operator report: {action['label']} {verdict} (observed cost {cost}). "
                 f"Affected assets: {', '.join(about) or 'none'}. {note}").strip(),
        "about": about, "created": iso_now()[:10],
    })
    return doc_id
