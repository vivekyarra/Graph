import ast
from pathlib import Path

ROOT=Path(__file__).parents[1]


def test_production_api_never_uses_test_graph_fallback():
    for name in ['api.py','agents.py','store.py']:
        src=(ROOT/'maelin'/name).read_text(encoding='utf-8')
        assert 'traversal_fallback(' not in src
        ast.parse(src)


def test_missing_falkordb_dependency_is_not_hidden():
    src=(ROOT/'maelin'/'api.py').read_text(encoding='utf-8')
    assert 'HTTPException(503' in src
    assert 'store().ready' in src
    assert 'falkordb' in (ROOT/'requirements.txt').read_text().lower()


def test_mcp_has_no_arbitrary_query_tool():
    src=(ROOT/'maelin'/'mcp_server.py').read_text(encoding='utf-8')
    assert '@mcp.tool()' in src
    assert 'query_write' not in src
    assert 'execute_cypher' not in src


def test_production_logic_has_no_python_graph_traversal():
    src=(ROOT/'maelin'/'logic.py').read_text(encoding='utf-8')
    assert 'def traversal_fallback' not in src
    assert 'def dfs(' not in src
    assert (ROOT/'tests'/'offline_graph.py').exists()


def test_dynamic_graph_and_mcp_judge_requirements_are_wired():
    api=(ROOT/'maelin'/'api.py').read_text(encoding='utf-8')
    agents=(ROOT/'maelin'/'agents.py').read_text(encoding='utf-8')
    assert '@api.post("/api/scenarios"' in api
    assert '/api/conversation/' in api
    assert 'reason_with_tools(' in agents
    assert 'graph_tool(' in agents
    assert 'call_tool(' in (ROOT/'maelin'/'mcp_client.py').read_text(encoding='utf-8')
    assert '.edge.cut' in (ROOT/'static'/'cockpit.css').read_text(encoding='utf-8')


def test_seed_data_is_synthetic_and_all_relations_have_known_endpoints():
    import json
    d=json.loads((ROOT/'data'/'demo.json').read_text(encoding='utf-8'))
    ids={x['id'] for x in d['assets']}
    for e in d['pivot_edges']+d['depends_edges']:
        assert e['from'] in ids and e['to'] in ids
    pivot_ids={x['id'] for x in d['pivot_edges']}
    for a in d['actions']:
        assert set(a['blocked_edges']).issubset(pivot_ids)
        assert set(a['blocked_nodes']).issubset(ids)
