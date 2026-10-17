"""Tests for Vercel serverless deployment configuration and entrypoint."""
import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_vercel_entrypoint_exposes_fastapi_app():
    from api.index import app
    from maelin.api import api

    assert isinstance(app, FastAPI)
    assert app is api

    client = TestClient(app)
    # Root path returns Cockpit UI
    resp = client.get("/")
    assert resp.status_code == 200
    assert "html" in resp.headers.get("content-type", "").lower()
    assert "MAELIN" in resp.text

    # Static assets mounted under /assets
    resp_css = client.get("/assets/cockpit.css")
    assert resp_css.status_code == 200
    assert "css" in resp_css.headers.get("content-type", "").lower()

    resp_js = client.get("/assets/cockpit.js")
    assert resp_js.status_code == 200
    assert "javascript" in resp_js.headers.get("content-type", "").lower()


def test_vercel_json_routes_configuration():
    repo_root = Path(__file__).resolve().parent.parent
    vercel_path = repo_root / "vercel.json"
    assert vercel_path.is_file(), "vercel.json must exist in project root"

    with open(vercel_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    assert "routes" in config, "vercel.json must configure routes"
    routes = config["routes"]

    # Check asset route: /assets/(.*) -> static/$1
    asset_routes = [r for r in routes if r.get("src") == "/assets/(.*)"]
    assert len(asset_routes) == 1, "Must route /assets/(.*) to static/$1"
    assert asset_routes[0].get("dest") == "static/$1"

    # Check API route: /api/(.*) -> api/index.py
    api_routes = [r for r in routes if r.get("src") == "/api/(.*)"]
    assert len(api_routes) == 1, "Must route /api/(.*) to api/index.py"
    assert api_routes[0].get("dest") == "api/index.py"

    # Check root route: / -> api/index.py
    root_routes = [r for r in routes if r.get("src") == "/"]
    assert len(root_routes) == 1, "Must route / to api/index.py"
    assert root_routes[0].get("dest") == "api/index.py"


def test_render_yaml_removed():
    repo_root = Path(__file__).resolve().parent.parent
    render_yaml = repo_root / "render.yaml"
    assert not render_yaml.exists(), "render.yaml must be deleted"


def test_static_index_persistence_advisory_references_vercel():
    repo_root = Path(__file__).resolve().parent.parent
    index_html = (repo_root / "static" / "index.html").read_text(encoding="utf-8")
    assert "VERCEL SERVERLESS" in index_html
    assert "Render" not in index_html


def test_deployment_documentation_updated_for_vercel():
    repo_root = Path(__file__).resolve().parent.parent
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    deployment = (repo_root / "docs" / "deployment.md").read_text(encoding="utf-8")

    for doc_name, text in [("README.md", readme), ("docs/deployment.md", deployment)]:
        assert "https://vercel.com/golden-state-warriors" in text, f"{doc_name} must link to Vercel team"
        assert "FALKOR_SSL" in text, f"{doc_name} must explain FalkorDB SSL connection"
        assert "render.yaml" not in text.lower(), f"{doc_name} must not reference render.yaml"
        assert "on render" not in text.lower(), f"{doc_name} must not reference on Render"

