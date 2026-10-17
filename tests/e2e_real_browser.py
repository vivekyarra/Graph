"""REAL browser + REAL FalkorDB+FastAPI integration; no response mocking.

CI starts the Docker Compose app and seeds alpha/beta before running.
Playwright records a video and screenshots for human review, but those are
*engineering evidence*, not a substitute for the participant's own demo video.
"""
from __future__ import annotations
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path('browser_artifacts')
OUT.mkdir(exist_ok=True)
steps = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
    ctx = browser.new_context(viewport={'width': 1440, 'height': 920},
                              record_video_dir=str(OUT),
                              record_video_size={'width': 1440, 'height': 920})
    page = ctx.new_page()
    page_errors = []
    page.on('pageerror', lambda exc: page_errors.append(str(exc)))

    def dialogue(d):
        if d.type == 'prompt':
            d.accept('revoke-admin-role')
        else:
            d.accept()
    page.on('dialog', dialogue)
    page.goto('http://127.0.0.1:8000/', wait_until='domcontentloaded',timeout=30000)
    page.wait_for_function("document.querySelector('#connectivity').textContent.includes('connected')")
    page.locator('#investigate').click()
    page.wait_for_function("document.querySelector('#pathsCount').textContent.trim()==='2'")
    assert 'SAME DECISION' in page.locator('#memory').inner_text()
    assert page.evaluate("current.handoffs.some(h=>h.agent==='mcp' && h.payload.transport==='stdio')")
    page.screenshot(path=str(OUT/'01_cold_graph.png'),full_page=True)
    page.locator('#vulnerable').select_option('vault-sync')
    page.locator('#investigate').click()
    page.wait_for_function("document.querySelector('#pathsCount').textContent.trim()==='1'")
    page.screenshot(path=str(OUT/'01b_dynamic_node_investigation.png'),full_page=True)
    steps.append('User-selected vault-sync incident yields one live graph-derived route')
    page.locator('#vulnerable').select_option('auth-service')
    page.locator('#investigate').click()
    page.wait_for_function("document.querySelector('#pathsCount').textContent.trim()==='2'")
    steps.append('Cold attack paths 2; no-memory ablation is equal')

    page.locator('#simulate').click()
    page.wait_for_function("document.querySelector('#simulation').textContent.includes('MODELED ROUTES CONTAINED')")
    assert '2 before' in page.locator('#simulation').inner_text() or '2 → 0' in page.locator('#simulation').inner_text()
    page.screenshot(path=str(OUT/'02_real_graph_clone_replay.png'),full_page=True)
    steps.append('Native FalkorDB graph-copy replay: 2 paths to 0')

    page.locator('#record').click()
    page.wait_for_timeout(600)
    page.locator('#newSession').click()
    page.wait_for_function("document.querySelector('#memory').textContent.includes('DECISION CHANGED')")
    assert 'rotate-auth-credentials' in page.locator('#memory').inner_text()
    page.screenshot(path=str(OUT/'03_causal_memory_ablation.png'),full_page=True)
    steps.append('Graph-stored operator report changed decision; no-memory ablation visible')

    page.locator('#drift').click()
    page.wait_for_timeout(650)
    page.locator('#newSession').click()
    page.wait_for_function("document.querySelector('#pathsCount').textContent.trim()==='3'")
    assert page.evaluate("current.analysis.recommended.action_ids.includes('invalidate-attacker-session')")
    page.screenshot(path=str(OUT/'04_topology_drift.png'),full_page=True)
    steps.append('Graph-derived topology drift: third threat path forces different plan')
    assert not page_errors, f'Unhandled JS errors: {page_errors}'
    video = page.video
    ctx.close()
    video.save_as(str(OUT/'maelin_real_graph_walkthrough.webm'))
    browser.close()

result = {'integration': 'REAL FalkorDB + FastAPI + Chromium, no API mocks',
          'steps': steps, 'javascript_errors':page_errors,
          'limitations': 'Synthetic security scenario, operator report is a simulation, no cloud systems touched.'}
(OUT/'browser_proof.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result,indent=2))
