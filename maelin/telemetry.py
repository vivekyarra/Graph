"""FalkorDB execution telemetry: one trace row per Cypher round trip.

The wrapper records the graph, the agent that issued the query, whether it was
``GRAPH.RO_QUERY`` or ``GRAPH.QUERY``, the parameterized Cypher text and the
duration FalkorDB itself reports (``run_time_ms`` - GraphBLAS / execution time,
not Python wall-clock). Traces are scoped per investigation with a ContextVar,
so concurrent requests never share or leak each other's evidence.

Queries executed inside the MCP subprocess are returned by each tool as a
``telemetry`` list and merged by ``maelin.agents.graph_tool``.
"""
from contextlib import contextmanager
from contextvars import ContextVar

_TRACE = ContextVar("maelin_execution_trace", default=None)


def _clean(cypher, limit=500):
    return " ".join(str(cypher).split())[:limit]


def _graph_name(graph):
    return getattr(graph, "name", None) or getattr(graph, "graph_name", None) or "unknown"


@contextmanager
def telemetry_scope():
    """Collect every traced query issued in this context."""
    existing = _TRACE.get()
    if existing is not None:
        yield existing
        return
    trace = []
    token = _TRACE.set(trace)
    try:
        yield trace
    finally:
        _TRACE.reset(token)


def current_trace():
    return list(_TRACE.get() or [])


def merge_trace(entries):
    """Merge telemetry returned by an out-of-process MCP tool call."""
    target = _TRACE.get()
    if target is None or not entries:
        return
    for entry in entries:
        if isinstance(entry, dict):
            target.append(entry)


def traced_query(graph, cypher, params=None, *, agent_name, query_type="ro_query",
                 evidence_id=None):
    """Execute one FalkorDB query unchanged and record its server-side timing."""
    runner = getattr(graph, query_type)
    result = runner(cypher, params) if params is not None else runner(cypher)
    run_time = getattr(result, "run_time_ms", None)
    try:
        run_time = round(float(run_time), 3)
    except (TypeError, ValueError):
        run_time = None
    trace = _TRACE.get()
    if trace is not None:
        trace.append({
            "graph_name": _graph_name(graph),
            "agent_name": agent_name,
            "query_type": query_type,
            "cypher": _clean(cypher),
            "run_time_ms": run_time,
            "evidence_id": evidence_id,
        })
    return result
