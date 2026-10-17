# Maelin Automatic Deployment & Persistent Architecture

Production demo URL: https://maelin-graph-hacks-demo.onrender.com  
Render service: https://dashboard.render.com/web/srv-db9imegm7kps73dhnkj0  
Repository: https://github.com/vivekyarra/Graph  
Production branch: `main`  
Demo Docker build: `Dockerfile.demo`  
Production Docker build: `Dockerfile` (requires persistent FalkorDB)

---

## 1. Ephemeral Container Limitation vs. Persistent Memory

### The Current Ephemeral Demo Architecture
In the standalone hackathon demo (`Dockerfile.demo`), both FalkorDB and the FastAPI application run together inside a single Render web service container. This enables a frictionless, zero-setup public demo where judges can test the full graph engine immediately without configuring external cloud credentials.

However, **Render's container filesystem is ephemeral**:
- Whenever Render auto-deploys a new commit, restarts an idle container, or spins up a fresh instance, the local container filesystem is discarded and recreated.
- On each container startup, `scripts/start-demo.sh` executes `python -m maelin.seed` to populate the default `alpha` and `beta` topologies.
- **Consequence**: Any learned incident history (Track 02: `Episode -> ActionExperience` memory nodes), operator-reported unexpected outages, causal score adaptations, and uploaded custom tenant graphs are reset back to baseline.

### Automated Code Delivery vs. State Persistence
The automatic deployment pipeline (GitHub Actions CI + Render Auto-Deploy on `main`) automates **code delivery**:
- Every push to `main` triggers automated verification across Python integration, live FalkorDB Cypher traversal, and Chromium browser tests.
- When CI passes, Render automatically pulls the latest commit, builds the container image, and performs a zero-downtime rolling deployment.

However, **automatic code deployment does not solve data persistence**. To ensure that Maelin's learned graph memory, incident handoffs, and operator feedback endure across code updates, FalkorDB must be decoupled from the application container and hosted on persistent infrastructure.

---

## 2. Setting Up Persistent FalkorDB Hosting

To transition from the ephemeral demo container to durable production memory, configure an external persistent FalkorDB instance and switch the Render deployment to the decoupled `Dockerfile`.

### Option A: FalkorDB Cloud (Recommended Managed Hosting)
1. **Create an Instance**:
   - Register at [FalkorDB Cloud](https://app.falkordb.cloud).
   - Create a database cluster in the region closest to your Render service (e.g., Singapore `sin`, Oregon `ore`, or Frankfurt `fra`).
   - Select your desired sizing and enable persistent SSD storage and automated snapshots.
2. **Collect Connection Details**:
   - Hostname (e.g., `db-cluster-xyz.falkordb.cloud`)
   - Port (e.g., `6379` or custom SSL port)
   - Password / Auth token
   - Username (default: `default`)
   - Enable SSL (`FALKOR_SSL=1`)

### Option B: Self-Hosted FalkorDB with Persistent Volumes
Run FalkorDB on persistent infrastructure (e.g., AWS EC2, GCP Compute Engine, DigitalOcean Droplet, or a Render Private Service with a Persistent Disk):

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

The `--save 60 1` and `--appendonly yes` directives ensure point-in-time snapshots (RDB) and append-only logging (AOF) are continuously flushed to persistent storage.

---

## 3. Configuring Render for Persistent Hosting

Once your persistent FalkorDB instance is provisioned:

1. **Update Render Build Configuration**:
   - In Render Dashboard > Service Settings, set **Dockerfile Path** to `./Dockerfile` (or deploy via `render.yaml` which uses `./Dockerfile` by default).
   - Unlike `Dockerfile.demo`, `Dockerfile` is a lightweight Python container that does not run an internal Redis/FalkorDB server and instead connects to external hosting.

2. **Configure Environment Variables in Render**:
   In Render > Service > **Environment**:

   | Variable | Value / Description | Sensitive |
   |---|---|---|
   | `FALKOR_HOST` | Remote FalkorDB endpoint (e.g., `db.falkordb.cloud` or private IP) | No |
   | `FALKOR_PORT` | Port (e.g., `6379`) | No |
   | `FALKOR_PASSWORD` | Strong database password / auth token | **Yes** |
   | `FALKOR_USERNAME` | Database username (default: `default`) | No |
   | `FALKOR_SSL` | `1` (mandatory for FalkorDB Cloud TLS connections) | No |
   | `MAELIN_OPERATOR_TOKEN` | Cryptographically random secret for authenticated graph mutations | **Yes** |
   | `MAELIN_AGENT_TOOLS` | `mcp` (activates stdio FastMCP agent tools) | No |
   | `MAELIN_ENABLE_DEMO_MUTATIONS` | `1` to allow demo operators to test simulations/drift, or `0` for production lock | No |
   | `OPENAI_API_KEY` | (Optional) API key for optional LLM reasoning mode | **Yes** |
   | `MAELIN_LLM_MODEL` | `gpt-4o-mini` (or your preferred OpenAI/Ollama model) | No |

3. **One-Time Seed for Remote Persistent Graph**:
   Run the seeding script against your remote FalkorDB instance from your workstation or a CI pipeline task:

   ```bash
   export FALKOR_HOST="your-remote-host"
   export FALKOR_PORT="6379"
   export FALKOR_PASSWORD="your-secure-password"
   export FALKOR_SSL="1"

   python -m maelin.seed --tenant alpha
   python -m maelin.seed --tenant beta
   ```

4. **Verify Deployment Health**:
   - After Render finishes deploying `Dockerfile`, check the health endpoint:
     ```bash
     curl -s https://maelin-graph-hacks-demo.onrender.com/api/health?tenant=alpha
     # Returns: {"graph_required":true,"seeded":true,"tenant":"alpha"}
     ```
   - Future git pushes to `main` will automatically build and deploy new application code without touching the remote FalkorDB data.
   - Operator reports (`/api/outcome`), causal ablation memory, and custom tenant uploads will now persist indefinitely.

---

## 4. Release Automation Workflow

1. **GitHub Actions Validation**:
   - `falkordb-integration.yml`: Runs unit tests, invariant checks, live FalkorDB Cypher queries, and headless Chromium browser tests.
   - `demo-container.yml`: Builds and tests the standalone container smoke test.
2. **Auto-Deploy on Render**:
   - Service is connected directly to the GitHub repository `vivekyarra/Graph`.
   - Set **Auto-Deploy: After CI Checks Pass** in Render Settings to ensure only verified commits reach production.
   - Zero duplicate webhooks or manual redeploy triggers needed.
