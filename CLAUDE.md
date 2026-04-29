# Synaptic Fabric — Nexus Edition

Autonomous IIoT predictive-maintenance platform that simulates a 4-node
manufacturing chain and uses physics-informed AI + an n8n agent loop to
predict, justify, and mitigate failures locally with no cloud dependency.

---

## 1. Manufacturing chain

```
M_1 Induction Motor  ->  M_2 Industrial Gearbox  ->
M_3 CNC Milling Tool ->  M_4 Robotic Sorting Arm
```

Causality (with physics-based delay buffers, not random):

```
torque spike (M_1) -> vibration (M_2) -> thermal runaway (M_3) -> overstrain (M_4)
```

Implemented in [digital_twin/simulator.py](digital_twin/simulator.py) using
per-edge `deque` buffers (`PROPAGATION_DELAY` of 2 / 3 / 4 ticks) so an
upstream torque spike measurably shows up downstream a few ticks later.

Health states per node: `Healthy` (emerald), `Warning` (amber),
`Critical` (crimson) — derived from the fused prediction in
[backend_fastapi/ai_engine/machine_analyzer.py](backend_fastapi/ai_engine/machine_analyzer.py).

Dataset base for the original failure model: AI4I 2020 Predictive
Maintenance ([data/predictive_maintenance_dataset_expanded.csv](data/predictive_maintenance_dataset_expanded.csv)).

---

## 2. AI Trinity

| Component | Where | Purpose |
|---|---|---|
| **PINN** (Heat-equation Physics-Informed NN) | [pinn_model/heat_pinn.py](pinn_model/heat_pinn.py), [pinn_model/pinn_inference.py](pinn_model/pinn_inference.py) | Predicts steady-state temperature; gap vs measured temp drives `pinn_risk` |
| **GNN** (chain-aware) | [ml_models/gnn_model.py](ml_models/gnn_model.py), [ml_models/gnn_inference.py](ml_models/gnn_inference.py), [ml_models/graph_builder.py](ml_models/graph_builder.py) | Inductive failure propagation along the chain |
| **Agentic RAG** | [backend_fastapi/chatbot/](backend_fastapi/chatbot/), [vectordb/](vectordb/) | Local LLM (Ollama/phi3) with manual citations |

Chain encoding for the GNN: row-normalized directed adjacency,
`M_i -> M_{i+1}` (1.0), self-loop (1.0), weak reverse (0.25 for
upstream attribution). See [ml_models/graph_builder.py](ml_models/graph_builder.py).

The fused per-machine prediction is:

```
prediction = 0.40 * failure_probability   # ML
           + 0.20 * anomaly_score         # physics + ML anomaly
           + 0.15 * gnn_risk              # chain propagation
           + 0.15 * pinn_risk             # heat-eq deviation
           + 0.10 * ml_anomaly
```

with a hard physics override that pins risk >= 0.9 if any of
`tool_wear > 0.9`, `temperature > 315`, `vibration > 0.85`.

---

## 3. Chatbot architecture (two-tier, fully local)

The dashboard chatbot is intentionally **not** routed through n8n —
n8n adds HTTP-hop latency and has no place in an interactive chat
path. `/chat/stream` is a single-process two-tier router optimized
for `phi3:mini` on CPU:

```
user question
   |
   v
[fast deterministic path]   <-- regex pattern match against LIVE_MACHINES
   |  metric lookups, status, comparisons, plant health, alerts
   |  ~10-300 ms, NO LLM call
   v
[LLM reasoning path]        <-- only when reasoning words appear
   (why / explain / how / should I / cause / suggest / trend / history)
   - slim prompt (focused machine; history added only when explicitly asked)
   - num_predict=80, num_ctx=1024, num_thread=8
   - streamed back as text/plain, token by token (typing effect)
```

The fast path resolves the vast majority of real-time queries
("what is temp of M_2?", "which is worst?", "status of M_3") in
under a second without invoking the LLM at all. The LLM is reserved
for queries that genuinely need reasoning.

- Endpoint: [backend_fastapi/app/chatbot_api.py](backend_fastapi/app/chatbot_api.py)
- LLM client: [backend_fastapi/chatbot/llm_client.py](backend_fastapi/chatbot/llm_client.py)
- Frontend (streaming consumer with typing effect, Stop button):
  [frontend_dashboard/src/components/Chatbot.js](frontend_dashboard/src/components/Chatbot.js)
- Model warmup runs in a background thread on FastAPI startup so the
  first user query isn't extra-slow (see `_warmup_llm_on_start` in
  [backend_fastapi/app/main.py](backend_fastapi/app/main.py)).

The legacy `/chat` endpoint is kept as a non-streaming fallback that
shares the same fast/LLM routing.

---

## 4. n8n Agent Pipeline (closed loop)

n8n Community Edition runs **locally in Docker** and acts as the agent
brain. The shape:

```
FastAPI (alert)
   |  POST http://localhost:5678/webhook/synfab-alert
   v
[Webhook] -> [Normalize] -> [Switch on severity]
                                 |             \
                            CRITICAL          WARNING
                                 |               |
                       [Ollama phi3 - cite]   (skip LLM)
                                 |               |
                                 v               v
       POST /agent/action (FastAPI)   POST /agent/action (FastAPI)
            AUTO_MAINTENANCE                NOTIFY_OPERATOR
```

- Workflow JSON: [n8n/workflows/synaptic_fabric_agent.json](n8n/workflows/synaptic_fabric_agent.json)
- Outbound from FastAPI: [backend_fastapi/app/n8n_client.py](backend_fastapi/app/n8n_client.py)
  (fire-and-forget, throttled per machine, fails silently if n8n is down)
- Inbound webhook to FastAPI: [backend_fastapi/app/agent_webhook.py](backend_fastapi/app/agent_webhook.py)
  exposing `POST /agent/action`, `GET /agent/actions`, `GET /agent/health`
- `AUTO_MAINTENANCE` resets the digital-twin state for the target machine
  (tool_wear *= 0.15, vibration *= 0.25, temp -= 8, torque *= 0.92), so the
  closed loop is observable in the dashboard
- Local auto-maintenance (in `main.py`, independent of n8n) fires when a
  machine has dwelled in `Critical` for `CRITICAL_DWELL_SECONDS = 10` and
  is not within the per-machine cooldown window. It emits two
  `agent_actions` entries — `STARTING` then `SUCCESS` — which the frontend
  picks up to show the upper-center popup (`⚙️ Performing maintenance on
  M_x` → `✅ Maintenance completed for M_x`).
- See [n8n/README.md](n8n/README.md) for the import + activation steps

---

## 5. Stack

- **Backend:** FastAPI (Python 3.11+; this repo runs on 3.14 via `venv/`)
- **Frontend:** React (CRA) with `@react-three/fiber` + `drei` for the
  digital-twin scene, `recharts` for the temperature chart
- **Orchestration:** n8n Community (self-hosted Docker)
- **Vector DB:** Qdrant (self-hosted Docker)
- **LLM runtime:** Ollama (self-hosted Docker, model `phi3`)
- **Persistence:** SQLite ([machine_data.db](machine_data.db)) for live
  history; PostgreSQL is in the architecture brief but not wired in this
  build (SQLite is fine for the local demo)
- **Infra:** [docker-compose.yml](docker-compose.yml) ships n8n, Qdrant,
  and Ollama. Backend + frontend run on the host.

---

## 6. Repo layout

```
backend_fastapi/
  ai_engine/
    machine_analyzer.py     # GNN + PINN + ML + anomaly fusion
    root_cause.py           # per-machine root-cause rules (4 nodes)
  app/
    main.py                 # FastAPI entrypoint, WS stream, history, maintenance
    agent_webhook.py        # /agent/action, /agent/actions, /agent/health
    n8n_client.py           # outbound alerts to n8n
    chatbot_api.py          # /chat + /chat/stream (two-tier router)
    state.py                # LIVE_MACHINES dict
  chatbot/                  # llm_client (Ollama), history_tools, RAG
  database/                 # SQLAlchemy models + session
  analytics/                # plant-level analytics

digital_twin/
  simulator.py              # 4-node causal-physics simulator (M_1..M_4)

ml_models/
  graph_builder.py          # chain-encoded adjacency
  gnn_model.py              # SimpleGNN
  gnn_inference.py          # row-normalized message passing
  failure_model.py          # ML failure probability
  anomaly_model.py          # ML anomaly
  transformer_inference.py  # short-horizon temp forecast
  explainer.py              # SHAP

pinn_model/
  heat_pinn.py              # Physics-informed network (heat eq.)
  pinn_inference.py         # predict_temp(temp, torque, air)

frontend_dashboard/src/
  App.js                    # Mission Control dashboard
  useMachineStream.js       # WS client, popup queue
  components/
    MachineCard.js          # per-machine card (uses MACHINE_INFO)
    FactoryTwin3D.js        # 3D twin with name labels per machine
    TemperatureChart.js     # 4 lines (M_1..M_4) with named series
    AlertPanel.js
    Chatbot.js
  utils/machineInfo.js      # name + process + stage for M_1..M_4

n8n/
  workflows/synaptic_fabric_agent.json
  README.md

docker-compose.yml          # n8n, Qdrant, Ollama (all local)
```

---

## 7. WebSocket payload (per tick, ~1 Hz)

```jsonc
{
  "machines": [                   // 4 entries, M_1..M_4 in chain order
    {
      "machine_id": "M_3",
      "temperature": 296.06,
      "torque": 44.18,
      "tool_wear": 0.1024,
      "vibration_index": 0.1531,
      "pinn_temperature": 275.485, // PINN heat-eq prediction
      "pinn_risk": 0.0,
      "gnn_risk": 0.0,
      "anomaly_score": 0.063,
      "failure_probability": 0.121,
      "prediction": 0.121,         // fused final risk
      "rul_cycles": 280,
      "rul_time": "5.6 hrs",
      "health_status": "Healthy",
      "root_cause": [...],
      "alerts": [...],
      "shap": {...}
    }
  ],
  "factory_analytics": {
    "plant_health_score": 88.2,
    "most_unstable_machine": "M_4",
    "total_machines": 4,
    "machines_needing_attention": []
  },
  "agent_alerts":  [ /* WARNING/CRITICAL */ ],
  "agent_actions": [ /* local + n8n-applied actions */ ]
}
```

---

## 8. Running locally

### Backend (host)

```bash
cd D:/spm/SynapticFabricnew
./venv/Scripts/python.exe -m uvicorn backend_fastapi.app.main:app \
  --host 0.0.0.0 --port 8000
```

The entrypoint reconfigures stdout/stderr to UTF-8 — required on Windows
with Python 3.14, otherwise the codebase's emoji `print()` calls trip
`cp1252` and bubble out as 500s from request handlers (this was the
"API error" fixed during the last session). See
[backend_fastapi/app/main.py:1-15](backend_fastapi/app/main.py:1).

### Frontend (host)

```bash
cd frontend_dashboard
npm start         # http://localhost:3000
```

### Local services (Docker)

```bash
docker compose up -d n8n qdrant ollama
docker exec -it synfab_ollama ollama pull phi3   # one-time
```

Then open http://localhost:5678, create a local owner account, import
[n8n/workflows/synaptic_fabric_agent.json](n8n/workflows/synaptic_fabric_agent.json), and **Activate** it.

---

## 9. Endpoints

| Method | Path | Purpose |
|---|---|---|
| `WS` | `/ws/machines` | Live stream (machines, analytics, alerts, actions) |
| `GET` | `/history?minutes=N` | Per-machine temperature history (M_1..M_4) |
| `POST` | `/maintenance/{machine_id}` | Manual maintenance reset |
| `POST` | `/agent/action` | Closed-loop hook called by n8n |
| `GET` | `/agent/actions` | Recent agent actions log |
| `GET` | `/agent/health` | Liveness probe |
| `POST` | `/chat` | Chatbot (non-streaming fallback, same two-tier routing) |
| `POST` | `/chat/stream` | Chatbot (streamed `text/plain`, fast path + LLM) |

---

## 10. Key design decisions

- All services self-hosted; no cloud dependency.
- Causal propagation uses physics-based delay queues, not RNG.
- PINN loss is a heat-equation residual; inference contributes a
  dedicated `pinn_risk` term to the fused prediction.
- GNN uses a chain-encoded, row-normalized adjacency (not fully connected).
- Chatbot uses fast deterministic routing for real-time queries and only
  falls through to the LLM when reasoning is required — n8n is
  deliberately kept out of the chat path for latency reasons.
- Auto-maintenance fires on a **dwell-time** rule (10s in `Critical`),
  not on a strict metric threshold, so high-risk machines are reliably
  serviced even when individual signals (e.g. `tool_wear`) stay low.
- n8n webhooks drive the closed-loop corrective actions outside the chat
  path (alert → severity switch → corrective POST back to FastAPI).
- Frontend follows a "Mission Control" industrial dark theme; machine
  cards, the 3D twin, and the temperature chart all show the human
  machine names from [frontend_dashboard/src/utils/machineInfo.js](frontend_dashboard/src/utils/machineInfo.js).

---

## 11. Known gotchas

- **Windows + Python 3.14:** stdout must be UTF-8 (handled in `main.py`).
  If you ever copy `print(...)` with emoji into a fresh entrypoint,
  replicate the `reconfigure(encoding="utf-8", errors="replace")` block.
- **n8n down:** `n8n_client.py` swallows connection errors and throttles
  per machine, so the WS loop keeps running even when n8n isn't up.
- **Ollama model not pulled:** the n8n CRITICAL branch will error on the
  Ollama HTTP call; the WARNING branch and corrective-action POST still
  work. Pull `phi3` once with `ollama pull phi3`. The dashboard chatbot
  uses `phi3:mini` — pull that too if it's missing.
- **Chat fast path vs LLM path:** queries are routed to the fast
  deterministic answerer unless they contain reasoning words (`why`,
  `how`, `explain`, `cause`, `should`, `suggest`, `trend`, `history`,
  etc.). Adding one of these to a metric question forces the slower
  LLM path. The pattern lists are at the top of
  [backend_fastapi/app/chatbot_api.py](backend_fastapi/app/chatbot_api.py).
- `.gitignore` covers `venv/`, `__pycache__/`, `node_modules/`, `.env`.
  Don't commit `*.pyc`, `*.pth` retrains, or `machine_data.db`.
