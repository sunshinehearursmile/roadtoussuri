# Deployment

Two targets: a **local server** and **Google Cloud Run**. Both serve the same FastAPI
app (`web.app:app`) which hosts the browser UI at `/`, the game API at `/api/*`, and the
MCP tools at `/tools/*`.

## Environment

Copy `.env.example` → `.env` and set:

| var | purpose | default |
|---|---|---|
| `GROQ_API_KEY` | Groq key (`gsk_…`). Absent → deterministic offline LLM | — |
| `GROQ_MODEL` | model id | `llama-3.3-70b-versatile` |
| `GAME_CONFIG_PATH` / `PROMPTS_PATH` | YAML locations (relative to project root) | `config/…` |
| `DB_PATH` | SQLite file | `data/road_to_ussuri.db` |
| `WEB_HOST` / `WEB_PORT` | web bind (Cloud Run overrides with `PORT`) | `0.0.0.0` / `8080` |

> `.env` is git-ignored and `.dockerignore`d — never commit the key.

---

## 1. Local server

```bash
make install                 # venv + editable install
cp .env.example .env         # add GROQ_API_KEY

# both servers (web :8080 + MCP :8000):
./deploy/run_local.sh
# or individually:
make web                     # browser UI  → http://localhost:8080
make mcp                     # MCP server  → http://localhost:8000
make play                    # terminal game
```

Verify:

```bash
curl -s localhost:8080/health          # {"status":"ok","service":"web",...}
curl -s localhost:8000/health          # {"status":"ok","service":"mcp_server"}
curl -s localhost:8000/tools/create_session -H 'Content-Type: application/json' -d '{"class_id":"peasant_farmer"}'
```

Then open **http://localhost:8080** and play.

---

## 2. Docker (local container)

```bash
make docker-build
docker run --rm -p 8080:8080 -e GROQ_API_KEY=gsk_... road-to-ussuri
# → http://localhost:8080
```

The image installs runtime deps only (no google-adk / pytest), copies the source tree
(so `config/` resolves), and runs `python -m web.serve`, honouring Cloud Run's `$PORT`.

---

## 3. Google Cloud Run

### One command
```bash
PROJECT_ID=my-project GROQ_API_KEY=gsk_... ./deploy/deploy_cloud_run.sh
```
It enables the needed APIs, stores the key in **Secret Manager** (`groq-api-key`),
builds from the `Dockerfile` via Cloud Build, and deploys a public service. Optional:
`REGION` (default `europe-west1`), `SERVICE`, `GROQ_MODEL`, `ALLOW_UNAUTH`.

### Manual equivalent
```bash
gcloud config set project MY_PROJECT
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com

# secret
printf '%s' "$GROQ_API_KEY" | gcloud secrets create groq-api-key --data-file=- \
  || printf '%s' "$GROQ_API_KEY" | gcloud secrets versions add groq-api-key --data-file=-

# deploy
gcloud run deploy road-to-ussuri \
  --source . --region europe-west1 --allow-unauthenticated \
  --port 8080 --memory 512Mi --cpu 1 --min-instances 0 --max-instances 3 \
  --set-env-vars GROQ_MODEL=llama-3.3-70b-versatile \
  --set-secrets GROQ_API_KEY=groq-api-key:latest
```

`gcloud run services describe road-to-ussuri --region … --format='value(status.url)'`
gives the URL. Open it and play.

### Notes for Cloud Run
- **SQLite is ephemeral** (container-local `/tmp`). Fine for a hackathon / single-player
  sessions. For persistence, mount Cloud SQL or swap `db.py` for a networked DB.
- Scales to zero (`--min-instances 0`); first hit after idle is a cold start.
- Rotate the key by adding a new secret version — no rebuild needed.

---

## Changing balance or prompts without redeploy

Both YAMLs are the single source of truth. Edit them, then:

```bash
curl -s localhost:8000/tools/reload_config -H 'Content-Type: application/json' -d '{}'
# or:  rtu config-reload
```

The server re-reads `game_config.yaml` and `prompts.yaml` in place.
