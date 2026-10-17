# Maelin Vercel Deployment & Persistent Architecture

Vercel Team / Project: https://vercel.com/golden-state-warriors  
Repository: https://github.com/vivekyarra/Graph  
Production branch: `main`  
Vercel Serverless Entrypoint: `api/index.py`  
Vercel Configuration: `vercel.json`  

---

## 1. Vercel Serverless Architecture & FalkorDB Connection

### Stateless Serverless Functions vs. Persistent Graph Storage
Vercel runs applications as stateless serverless functions that spin up on demand, handle requests, and scale down to zero. 

Because **Vercel serverless functions cannot run an internal background Redis/FalkorDB daemon**:
- The FastAPI application running on Vercel acts purely as a stateless compute layer.
- All graph state, Cypher incident topology, agent handoff traces, and episodic memory (`Episode -> ActionExperience` nodes) reside in an external, persistent **FalkorDB** instance (e.g., [FalkorDB Cloud](https://app.falkordb.cloud) or a cloud VM with persistent SSD storage).
- The Vercel function connects directly to FalkorDB over TLS using standard environment variables: `FALKOR_HOST`, `FALKOR_PORT`, `FALKOR_PASSWORD`, `FALKOR_SSL=1`.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ VERCEL SERVERLESS DEPLOYMENT ARCHITECTURE                                              │
│                                                                                        │
│   git push main ──► GitHub Actions CI ──► Vercel GitHub Integration (Auto-Deploy)      │
│                                              │                                         │
│                                              ▼ (Edge Routing via vercel.json)          │
│                             ┌─────────────────────────────────┐                        │
│                             │     Vercel Global Edge CDN      │                        │
│                             └──────────────┬──────────────────┘                        │
│                                            │                                           │
│                  ┌─────────────────────────┴─────────────────────────┐                 │
│                  ▼                                                   ▼                 │
│     Static Assets (/assets/*)                             API & Cockpit UI (/ & /api/*)│
│     Routed to static/*                                    Routed to api/index.py       │
│     (cockpit.css, cockpit.js)                             (FastAPI Serverless App)     │
│                                                                      │                 │
│                                              TLS Connection (FALKOR_SSL=1)             │
│                                                                      ▼                 │
│                                                   ┌─────────────────────────────────┐  │
│                                                   │  Persistent FalkorDB Instance   │  │
│                                                   │  (FalkorDB Cloud / SSD Storage) │  │
│                                                   │  Graph Topology & Memory Stored │  │
│                                                   └─────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### Routing Architecture (`vercel.json`)
The application uses `vercel.json` to route traffic cleanly:
- **Static Assets**: Requests matching `/assets/(.*)` are served directly from `static/$1` by Vercel's global CDN (providing ultra-low latency for `cockpit.css` and `cockpit.js`).
- **Serverless API**: Requests matching `/api/(.*)` route directly to the serverless function `api/index.py` (which exposes `app = api`).
- **Cockpit UI Root**: Requests to `/` route to `api/index.py`, which serves `static/index.html`.

---

## 2. Setting Up Hosted FalkorDB

To provide persistent storage for the Vercel deployment:

### Option A: FalkorDB Cloud (Recommended Managed Hosting)
1. **Create an Instance**:
   - Register at [FalkorDB Cloud](https://app.falkordb.cloud).
   - Create a database cluster in your preferred region.
   - FalkorDB Cloud provides free and paid managed clusters with persistent SSD storage, automatic backups, and built-in TLS.
2. **Collect Connection Details**:
   - Hostname: `FALKOR_HOST` (e.g., `db-cluster-xyz.falkordb.cloud`)
   - Port: `FALKOR_PORT` (e.g., `6379`)
   - Password: `FALKOR_PASSWORD`
   - Username: `FALKOR_USERNAME` (default: `default`)
   - TLS: `FALKOR_SSL=1` (mandatory for FalkorDB Cloud TLS connections)

### Option B: Self-Hosted FalkorDB on a Persistent Cloud VM
Run FalkorDB with persistent volume storage (AWS EC2, GCP Compute Engine, DigitalOcean, etc.):

```bash
docker run -d \
  --name falkordb-prod \
  -p 6379:6379 \
  -v falkordb_persistent_data:/data \
  --restart unless-stopped \
  falkordb/falkordb:latest \
  --save 60 1 \
  --appendonly yes \
  --requirepass "YOUR_STRONG_DATABASE_PASSWORD"
```

The `--save 60 1` and `--appendonly yes` directives ensure point-in-time snapshots (RDB) and append-only logging (AOF) are continuously flushed to persistent disk storage.

---

## 3. Step-by-Step Vercel Deployment Guide

Deploying the repository to Vercel under your account (`https://vercel.com/golden-state-warriors`):

### 1. Import Project in Vercel
1. Navigate to the Vercel dashboard: [https://vercel.com/golden-state-warriors](https://vercel.com/golden-state-warriors).
2. Click **Add New...** > **Project**.
3. Under **Import Git Repository**, connect your GitHub account and select repository `https://github.com/vivekyarra/Graph`.
4. Leave the **Framework Preset** as default (**Other**).
5. Ensure the **Root Directory** is set to `./`.

### 2. Configure Environment Variables in Vercel
In the project configuration screen (or under **Settings** > **Environment Variables**), add the following:

| Variable | Value / Description | Sensitive |
|---|---|---|
| `FALKOR_HOST` | Remote FalkorDB endpoint (e.g., `db-xxx.falkordb.cloud` or cloud IP) | No |
| `FALKOR_PORT` | Port (e.g., `6379`) | No |
| `FALKOR_PASSWORD` | Database password / auth token | **Yes** |
| `FALKOR_USERNAME` | Database username (default: `default`) | No |
| `FALKOR_SSL` | `1` (enables TLS encryption for FalkorDB connections) | No |
| `MAELIN_OPERATOR_TOKEN` | Cryptographically random secret for authenticated graph mutations and topology inspection | **Yes** |
| `MAELIN_AGENT_TOOLS` | `mcp` (activates stdio FastMCP agent tools) | No |
| `MAELIN_ENABLE_DEMO_MUTATIONS` | `1` to allow demo operators to test simulations/drift, or `0` for production lock | No |
| `OPENAI_API_KEY` | (Optional) API key for optional LLM reasoning mode | **Yes** |
| `MAELIN_LLM_MODEL` | `gpt-4o-mini` (or your preferred OpenAI model) | No |

### 3. Deploy
1. Click **Deploy**.
2. Vercel automatically detects `requirements.txt`, provisions the Python serverless environment, packages `api/index.py`, and maps routes according to `vercel.json`.
3. Your deployment will receive a live URL (e.g., `https://graph-golden-state-warriors.vercel.app`).

### 4. One-Time Seed for Remote Persistent Graph
Seed the initial tenant topologies (`alpha` and `beta`) into your remote FalkorDB database. Run this command once from your local development workstation or CI pipeline:

```bash
export FALKOR_HOST="your-remote-falkordb-host"
export FALKOR_PORT="6379"
export FALKOR_PASSWORD="your-secure-password"
export FALKOR_SSL="1"

python -m maelin.seed --tenant alpha
python -m maelin.seed --tenant beta
```

### 5. Verify Deployment Health
Check the health endpoint on your live Vercel deployment:

```bash
curl -s "https://<your-vercel-domain>.vercel.app/api/health?tenant=alpha"
# Expected response: {"graph_required":true,"seeded":true,"tenant":"alpha"}
```

Verify operator access and the interactive cockpit:
- Open `https://<your-vercel-domain>.vercel.app/` in your browser.
- The 3D graph cockpit will render immediately, reading directly from your hosted FalkorDB instance.

---

## 4. Release Automation Workflow

1. **GitHub Actions Validation**:
   - `falkordb-integration.yml`: Runs full test suite, Cypher graph traversal checks, invariant assertions, and headless browser tests on every push and pull request.
   - `demo-container.yml`: Smoke-tests standalone container builds.
2. **Auto-Deploy on Vercel**:
   - Vercel automatically watches `main` on `https://github.com/vivekyarra/Graph`.
   - Every verified commit pushed to `main` triggers an automatic zero-downtime deployment on Vercel.
   - Stateless functions update instantly without restarting or disrupting persistent FalkorDB data.
