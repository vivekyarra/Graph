# Maelin automatic deployment

Production demo URL: https://maelin-graph-hacks-demo.onrender.com
Render service: https://dashboard.render.com/web/srv-db9imegm7kps73dhnkj0
Repository: https://github.com/vivekyarra/Graph
Production branch: `main`
Docker build: `Dockerfile.demo`

## Release process

1. Push/merge a commit to `main`. GitHub Actions checks it using both
   `falkordb-integration.yml` (Python/live FalkorDB/Chromium) and
   `demo-container.yml` (standalone Docker graph/API smoke test).
2. Render service must be attached to **the GitHub provider**, not merely its
   public clone URL, for native auto-deploy to receive push events. Enable
   **Auto-Deploy: On Commit** or **After CI Checks Pass** in service Settings.
3. Confirm the new source commit appears in the Render deployment history and
   reaches `live`. Check `GET /api/health`: `seeded` should equal `true`.
4. For a production-grade gated release choose **After CI Checks Pass**;
   that waits until both GitHub Actions jobs for the commit succeed. Do not
   configure a deploy hook in addition to Render auto-deploy (duplicate builds).

## Important demo data caveat

`Dockerfile.demo` starts a real FalkorDB in the SAME ephemeral Render container.
This is suitable for a reproducible, temporary hackathon demonstration, **not**
for storing persistent outcomes. Every Render deploy/restart wipes incident
history. To keep learned memories across deployments, host FalkorDB separately
with persistent storage, then deploy `Dockerfile` and set the required
`FALKOR_*` variables in Render's private Environment settings.

Credentials: Keep `MAELIN_OPERATOR_TOKEN`, `OPENAI_API_KEY`, and database
secrets in Render Environment; never commit them to GitHub.
