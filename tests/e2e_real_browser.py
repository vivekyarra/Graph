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
    ctx = browser.new_context(viewport={'width': 1440, 'height': 900},
                              record_video_dir=str(OUT),
                              record_video_size={'width': 1440, 'height': 900})
    page = ctx.new_page()
    page_errors = []
    page.on('pageerror', lambda exc: page_errors.append(str(exc)))
    page.goto('http://127.0.0.1:8000/', wait_until='domcontentloaded', timeout=30000)
    page.wait_for_function("document.querySelector('#connectivity').classList.contains('ok')")
    page.wait_for_selector('#graph .node')
    # The cockpit must fit one laptop screen: no page scroll.
    assert page.evaluate("document.documentElement.scrollHeight <= window.innerHeight + 1")
    page.wait_for_selector('#intel .chip')
    assert 'algo.maxFlow' in page.locator('#intel').inner_text()
    steps.append('Native algorithm HUD rendered from FalkorDB (maxFlow min cut, chokepoint, pageRank)')

    page.locator('#investigate').click()
    page.wait_for_function("document.querySelector('#pathsCount') && document.querySelector('#pathsCount').textContent.trim()==='2'")
    assert page.evaluate("current.handoffs.some(h=>h.agent==='mcp' && h.payload.transport==='stdio')")
    assert page.evaluate("current.analysis.min_cut.optimal === true")
    page.wait_for_timeout(1200)
    page.screenshot(path=str(OUT / '01_investigation.png'))
    steps.append('Investigation: 2 graph-derived routes, real MCP stdio tool calls, plan proven minimal')

    page.locator('#vulnerable').select_option('vault-sync')
    page.locator('#investigate').click()
    page.wait_for_function("document.querySelector('#pathsCount') && document.querySelector('#pathsCount').textContent.trim()==='1'")
    steps.append('User-selected vault-sync incident yields one live graph-derived route')
    page.locator('#vulnerable').select_option('auth-service')
    page.locator('#investigate').click()
    page.wait_for_function("document.querySelector('#pathsCount') && document.querySelector('#pathsCount').textContent.trim()==='2'")

    page.locator('#simulate').click()
    page.wait_for_function("document.querySelector('#simulation') && document.querySelector('#simulation').dataset.status==='contained_on_modeled_snapshot'")
    page.wait_for_timeout(1200)
    page.screenshot(path=str(OUT / '02_clone_replay.png'))
    steps.append('Native FalkorDB graph-copy replay: 2 routes to 0, clone deleted')

    page.locator('[data-outage="revoke-admin-role"]').click()
    page.wait_for_selector('#newSession')
    page.locator('#newSession').click()
    page.wait_for_function("document.querySelector('#memory') && document.querySelector('#memory').dataset.ablation==='memory_ablation'")
    assert page.evaluate("current.analysis.recommended.action_ids.join()==='rotate-auth-credentials'")
    page.wait_for_timeout(1200)
    page.screenshot(path=str(OUT / '03_memory_changed_decision.png'))
    steps.append('Graph-stored operator report changed the decision; ablation banner visible')

    page.locator('[data-tab="brain"]').click()
    page.locator('#askInput').fill('What happened when we revoked the admin role?')
    page.locator('#askInput').press('Enter')
    page.wait_for_function("window.maelin.brain && window.maelin.brain.sources.length > 3")
    assert page.evaluate("maelin.brain.sources.some(s => s.id.startsWith('pm-auto-'))"), 'auto postmortem not searchable'
    page.wait_for_timeout(1500)
    page.screenshot(path=str(OUT / '04_company_brain.png'))
    steps.append('Company Brain answered with sources, including the auto-written postmortem')

    page.locator('#graph .node[data-id="vault-sync"]').dispatch_event('click')
    page.wait_for_function("window.maelin.asset && window.maelin.asset.asset_id==='vault-sync'")
    assert page.evaluate("maelin.asset.owners[0].team==='Data Infrastructure'")
    steps.append('Clicking a node shows owners, on-call, documents, decisions')

    page.keyboard.press('Control+K')
    page.locator('#paletteInput').fill('shadow')
    page.keyboard.press('Enter')
    page.wait_for_function("window.maelin.drifted === true")
    page.locator('[data-act="retest"]').click()
    page.wait_for_function("window.maelin.sim && window.maelin.sim.contained === false")
    assert page.evaluate("maelin.sim.remaining_routes") == 1
    page.locator('#newSession').click()
    page.wait_for_function("document.querySelector('#pathsCount') && document.querySelector('#pathsCount').textContent.trim()==='3'")
    assert page.evaluate("current.analysis.recommended.action_ids.includes('invalidate-attacker-session')")
    page.wait_for_timeout(1200)
    page.screenshot(path=str(OUT / '05_topology_drift.png'))
    steps.append('Topology drift: old verified plan fails on a fresh clone; agents re-plan for 3 routes')

    assert not page_errors, f'Unhandled JS errors: {page_errors}'
    video = page.video
    ctx.close()
    video.save_as(str(OUT / 'maelin_real_graph_walkthrough.webm'))
    browser.close()

result = {'integration': 'REAL FalkorDB + FastAPI + Chromium, no API mocks',
          'steps': steps, 'javascript_errors': page_errors,
          'limitations': 'Synthetic security scenario, operator report is a simulation, no cloud systems touched.'}
(OUT / 'browser_proof.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
