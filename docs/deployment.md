# MAELIN Deployment & Architecture Guide

Live Production Cockpit: [https://maelin-graph-hacks-demo.onrender.com](https://maelin-graph-hacks-demo.onrender.com)  
Repository: [https://github.com/vivekyarra/Graph](https://github.com/vivekyarra/Graph)  
Production Branch: `main`  
Configuration: `render.yaml` & `Dockerfile.demo`

---

## 1. Deployment Architecture on Render

MAELIN is deployed on **Render** as a high-performance containerized service combining FastAPI, FalkorDB, and the interactive single-screen cockpit.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ RENDER DEPLOYMENT ARCHITECTURE                                                         │
│                                                                                        │
│   git push origin main ──► Render Webhook / Auto-Deploy                                │
│                                  │                                                     │
│                                  ▼ (Builds via Dockerfile.demo)                        │
│                     ┌────────────────────────────────────────┐                         │
│                     │       Render Web Service (Docker)      │                         │
│                     │  maelin-graph-hacks-demo.onrender.com  │                         │
│                     │                                        │                         │
│                     │   ┌────────────────────────────────┐   │                         │
│                     │   │       FastAPI + Uvicorn        │   │                         │
│                     │   │       Static Cockpit Assets    │   │                         │
│                     │   └───────────────┬────────────────┘   │                         │
│                     │                   │ Loopback (6379)    │                         │
│                     │                   ▼                    │                         │
│                     │   ┌────────────────────────────────┐   │                         │
│                     │   │   Embedded FalkorDB Server     │   │                         │
│                     │   │   (falkordb.so + Redis engine) │   │                         │
│                     │   └────────────────────────────────┘   │                         │
│                     └────────────────────────────────────────┘                         │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Deploying on Render

### Method A: Automated Deployment via `render.yaml`
1. The repository root contains `render.yaml`, defining the `maelin-graph-hacks-demo` web service.
2. Render uses `Dockerfile.demo` which bundles:
   - Official `falkordb/falkordb-server` base image
   - Python 3.12 runtime + virtual environment
   - Automated startup script (`scripts/start-demo.sh`) that spins up FalkorDB, validates engine readiness, seeds synthetic tenants (`alpha` and `beta`), and boots FastAPI.

### Method B: Manual Re-Deploy & Cache Invalidation
If Render does not automatically trigger on push:
1. Open the [Render Dashboard](https://dashboard.render.com).
2. Select the **`maelin-graph-hacks-demo`** web service.
3. Click the **Manual Deploy** button in the top right.
4. Select **Clear build cache & deploy** (or **Deploy latest commit**).
5. Render will pull the latest commit from `main`, build the container, and serve the updated cockpit.

---

## 3. Environment Variables & Security Boundaries

| Variable | Recommended Value | Purpose |
|---|---|---|
| `MAELIN_PUBLIC_DEMO` | `1` | Allows tokenless inspection strictly for synthetic `alpha` and `beta` demo tenants. |
| `MAELIN_LOCAL_DEMO` | `1` | Enables local/demo exploration without requiring operator authentication tokens. |
| `MAELIN_ENABLE_DEMO_MUTATIONS` | `1` | Enables 1-click incident injection (`/api/demo/inject-shadow-route`) and state reset (`/api/demo/reset`). |
| `MAELIN_OPERATOR_TOKEN` | *(Secret Token)* | Required for production multi-tenant deployments to protect custom tenant data. |
| `FALKOR_HOST` | *(Optional Cloud Host)* | Defaults to `127.0.0.1` for container-bundled FalkorDB. Set to FalkorDB Cloud endpoint for external database. |
| `FALKOR_PORT` | `6379` | FalkorDB service port. |
| `FALKOR_PASSWORD` | *(Optional Cloud Password)* | Authentication password for external FalkorDB cluster. |
| `FALKOR_SSL` | `0` (or `1` for cloud) | Enables TLS encryption when communicating with external FalkorDB Cloud. |

---

## 4. Verifying the Live Deployment

Check the live service health endpoint:
```bash
curl -s "https://maelin-graph-hacks-demo.onrender.com/api/health?tenant=alpha"
```
Expected response:
```json
{"graph_required":true,"seeded":true,"tenant":"alpha"}
```

Open the live cockpit in your browser:
**[https://maelin-graph-hacks-demo.onrender.com](https://maelin-graph-hacks-demo.onrender.com)**
