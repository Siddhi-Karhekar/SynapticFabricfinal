# Synaptic Fabric — Nexus Edition

**Project Report**
Autonomous Industrial AI · Predictive Maintenance Platform
Repository: [`Siddhi-Karhekar/SynapticFabricfinal`](https://github.com/Siddhi-Karhekar/SynapticFabricfinal)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Architecture](#2-system-architecture)
3. [The Manufacturing Chain](#3-the-manufacturing-chain)
4. [The AI Trinity](#4-the-ai-trinity)
5. [Digital Twin Simulator](#5-digital-twin-simulator)
6. [Backend Service (FastAPI)](#6-backend-service-fastapi)
7. [Closed-Loop n8n Agent Pipeline](#7-closed-loop-n8n-agent-pipeline)
8. [Local Two-Tier Chatbot](#8-local-two-tier-chatbot)
9. [Maintenance Logging & Audit Trail](#9-maintenance-logging--audit-trail)
10. [What-If Spike Scenarios](#10-what-if-spike-scenarios)
11. [Auto-Maintenance Logic](#11-auto-maintenance-logic)
12. [Frontend Dashboard](#12-frontend-dashboard)
13. [Data Model & Persistence](#13-data-model--persistence)
14. [Deployment & Local Setup](#14-deployment--local-setup)
15. [Operational Gotchas](#15-operational-gotchas)
16. [Endpoint Reference](#16-endpoint-reference)
17. [WebSocket Payload Reference](#17-websocket-payload-reference)
18. [Tuning History (What Changed and Why)](#18-tuning-history-what-changed-and-why)
19. [Repository Structure](#19-repository-structure)
20. [Future Work & Known Limitations](#20-future-work--known-limitations)

---

## 1. Executive Summary

Synaptic Fabric is a **fully local, autonomous IIoT predictive-maintenance platform** that simulates a 4-node manufacturing chain in real time and uses a triad of AI models (a Physics-Informed Neural Network, a chain-aware Graph Neural Network, and classical ML predictors) to forecast failures, justify them with Retrieval-Augmented Generation (RAG), and self-correct via a local n8n agent loop — all without any cloud dependency.

The system is built around three principles:

1. **Physics first.** Every cross-machine effect is modelled with explicit causal-delay queues, not random noise. The PINN's loss is a heat-equation residual.
2. **Local-only.** n8n (Community Edition), Qdrant, and Ollama (`phi3` / `phi3:mini`) run in Docker on the host. No external API calls.
3. **Closed loop.** When a machine drifts into Critical, FastAPI fires a webhook into n8n; n8n routes on severity, asks `phi3` to justify the action, and posts a corrective `AUTO_MAINTENANCE` back to FastAPI which resets the digital-twin state — visible in the dashboard within seconds.

A React dashboard visualizes the four machines as both individual cards and a 3D digital twin, with collapsible panels for maintenance history, exports, and live temperature charts. An inline what-if spike feature lets operators perturb any machine's state and see the chain-effect ripple to the rest of the plant — fully reversible by any subsequent maintenance action.

The platform is engineered to demonstrate three things at once: **applied AI** (PINN + GNN + ML fusion + SHAP explainability), **agentic systems** (n8n-driven closed loop with cited-LLM reasoning), and **operational realism** (durable audit logs, what-if simulations, soft-failure handling when components like Ollama or n8n are offline).

---

## 2. System Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│  HOST                                                                  │
│                                                                        │
│  ┌─ FastAPI (uvicorn :8000) ────────────────────────────────────────┐  │
│  │   • WS /ws/machines     — 1 Hz live stream                       │  │
│  │   • Digital-twin tick   — physics propagation + 4 AI fusions     │  │
│  │   • DB writes           — MachineLog + MaintenanceLog (SQLite)   │  │
│  │   • REST endpoints      — /history, /maintenance, /spike, /chat  │  │
│  │   • n8n outbound        — fire-and-forget alerts on Warning+     │  │
│  │   • n8n inbound         — POST /agent/action  (corrective ops)   │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│            ▲                                                           │
│            │ WebSocket                                                 │
│  ┌─ React CRA (npm start :3000) ────────────────────────────────────┐  │
│  │   • App.js / MachineCard / FactoryTwin3D / Chatbot               │  │
│  │   • useMachineStream hook (popup queue, reconnect)               │  │
│  │   • Inter + JetBrains Mono · industrial control-room aesthetic   │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                        │
└──────────────────────────────────────┬─────────────────────────────────┘
                                       │ docker network (host-mapped)
                                       ▼
                ┌──────────────────────────────────────────┐
                │  DOCKER (docker-compose.yml)             │
                │                                          │
                │   ┌─ n8n        :5678  ───────┐          │
                │   │ Synaptic Fabric workflow  │          │
                │   │ Webhook → Switch → Ollama │          │
                │   │                  → REST   │          │
                │   └───────────────────────────┘          │
                │                                          │
                │   ┌─ Qdrant     :6333  ─┐                │
                │   │ Vector DB (RAG)     │                │
                │   └─────────────────────┘                │
                │                                          │
                │   ┌─ Ollama     :11434 ─┐                │
                │   │ phi3, phi3:mini      │               │
                │   └─────────────────────┘                │
                └──────────────────────────────────────────┘
```

### Why these boundaries

- **Host runs the realtime services** (FastAPI + React) because:
  - The simulator is CPU-bound and needs predictable scheduling.
  - The frontend dev loop is faster outside containers.
- **Docker holds the *infrastructure*** (n8n, Qdrant, Ollama) because:
  - They have stateful volumes that benefit from named-volume persistence.
  - Each upgrades on its own cadence and would otherwise pollute the host venv.
- **n8n is intentionally NOT in the chat path.** The dashboard chatbot's `/chat/stream` is a single-process two-tier router (regex fast path + slim LLM path); routing through n8n would add HTTP-hop latency to every keystroke.

---

## 3. The Manufacturing Chain

### Topology

```
M_1 Induction Motor  →  M_2 Industrial Gearbox  →
M_3 CNC Milling Tool →  M_4 Robotic Sorting Arm
```

Each machine runs as a stateful entry in `digital_twin/simulator.py::MACHINE_MEMORY`:

| Field | Range | Notes |
|---|---|---|
| `temperature` | 290 – 330 K | Clamped each tick |
| `torque` | 30 – 95 Nm | Wear-coupled + spike noise |
| `tool_wear` | 0 – 1 | Monotonically increasing in steady state |
| `vibration_index` | 0 – 1 | Self-decaying with upstream injection |

### Causal propagation

```
torque spike (M_1) → vibration (M_2) → thermal runaway (M_3) → overstrain (M_4)
```

Implemented with **explicit delay queues** (`PROP_BUFFERS`), not RNG. Each edge holds `delay` ticks of upstream values; what comes out is what went in `delay` seconds ago:

```python
PROPAGATION_DELAY = {
    "M_1->M_2": 2,   # torque spike reaches gearbox after ~2 ticks
    "M_2->M_3": 3,   # vibration drives milling thermal runaway
    "M_3->M_4": 4,   # thermal stress shows up as arm overstrain
}
```

This is what makes upstream → downstream effects **measurably delayed** in a way that shows up correctly in the dashboard charts (vibration spikes always lead temperature rises in M_3, etc.) and gives the GNN something to learn.

---

## 4. The AI Trinity

### 4.1 Physics-Informed Neural Network (PINN)

**Location:** [`pinn_model/heat_pinn.py`](pinn_model/heat_pinn.py), inference in [`pinn_model/pinn_inference.py`](pinn_model/pinn_inference.py).

Predicts the steady-state temperature a machine *should* be at, given its current thermal load and ambient air. The loss function is the residual of the 1-D heat equation, not a curve-fit on temperature data — the network learns the underlying physics.

The fused predictor uses the **gap** between PINN output and measured temperature:

```python
pinn_delta = max(0.0, pinn_temp - temperature)
pinn_risk = min(pinn_delta / 15.0, 1.0)
```

If the heat equation says the machine *will* be hot but it's currently cooler, that's an early indicator of developing thermal runaway and bumps risk. This is the explainable, physics-grounded leg of the trinity.

### 4.2 Chain-aware Graph Neural Network (GNN)

**Location:** [`ml_models/gnn_model.py`](ml_models/gnn_model.py), [`ml_models/gnn_inference.py`](ml_models/gnn_inference.py), [`ml_models/graph_builder.py`](ml_models/graph_builder.py).

Encodes the manufacturing chain as a directed graph with self-loops + weighted reverse edges (current weights):

```python
adj[i][i]    = 1.0    # self-loop
adj[i+1][i]  = 0.5    # downstream receives upstream
adj[i][i+1]  = 0.15   # weak reverse for attribution
# adj is then row-normalized so message passing is bounded.
```

After row normalization, each row's columns sum to 1 — node `i`'s GNN feature is a convex combination of its own state, its predecessor, and a small reverse echo from its successor.

The pretrained checkpoint at `ml_models/gnn.pth` was trained on raw unscaled features (`temperature` ~300, `torque` ~50). Its single `Linear(4,1)` produced near-constant logits that sigmoided to ~1.0 across all machines — a constant 0.15 floor on every fused prediction. **The current implementation bypasses the saturating model entirely** and replaces it with a chain-aware physics fallback:

```python
per_machine_risk = bounded([
    (T-290)/50 * 0.3 + tool_wear * 0.3 + vibration * 0.3 + (torque/100) * 0.1
    for each machine
])
chain_risk = adj @ per_machine_risk      # row-normalized message pass
```

This preserves the chain-aware semantic but produces sensible varying numbers (e.g. `M_3 GNN risk ≈ 0.18 ± 0.05` instead of `1.000`).

### 4.3 Classical ML stack

| Model | File | Role |
|---|---|---|
| Failure-probability model | `ml_models/failure_model.py` | Per-machine binary risk classifier (trained on AI4I 2020 dataset) |
| Anomaly detector (ML) | `ml_models/anomaly_model.py` | Unsupervised anomaly score |
| Transformer (short-horizon) | `ml_models/transformer_inference.py` | Future-temperature forecast over a 5–10 tick window |
| SHAP explainer | `ml_models/explainer.py` | Per-feature attribution for the failure predictor |

### 4.4 Fusion

The final per-machine prediction in `backend_fastapi/ai_engine/machine_analyzer.py`:

```python
prediction = (
    0.40 * failure_probability +   # ML
    0.20 * anomaly_score +         # physics + ML anomaly merged
    0.15 * gnn_risk +              # chain-aware
    0.15 * pinn_risk +             # heat-equation deviation
    0.10 * ml_anomaly              # ML anomaly model
)

# Hard physics override
if tool_wear > 0.9 or temperature > 315 or vibration > 0.85:
    prediction = max(prediction, 0.9)
elif tool_wear > 0.75 or temperature > 305 or vibration > 0.65:
    prediction = max(prediction, 0.7)
```

Health bins: `≥ 0.85 → Critical`, `≥ 0.5 → Warning`, else `Healthy`.

---

## 5. Digital Twin Simulator

**Location:** [`digital_twin/simulator.py`](digital_twin/simulator.py).

### Per-machine dynamics (one tick = ~1 second)

| Machine | Drives | Notes |
|---|---|---|
| **M_1 Induction Motor** | Torque baseline + 4%-probability spikes (`torque += U(8, 18)`). Tool wear gain `~0.0005/tick`. Temperature climbs slowly; bigger jump if torque > 70 (I²R heating). |
| **M_2 Industrial Gearbox** | Receives `delayed_torque` via `M_1→M_2` queue. Vibration: `0.985 · V_old + 0.0003 + 0.012 · delayed_torque + noise`. |
| **M_3 CNC Milling Tool** | Receives `delayed_vib` via `M_2→M_3` queue. Vibration: `0.94 · V_old + 0.18 · delayed_vib`. Heat: `friction_heat * 0.4 + vib_heat * 0.15`. |
| **M_4 Robotic Sorting Arm** | Receives `delayed_heat` via `M_3→M_4` queue. Vibration & torque coupled to upstream heat. |

### Shared mechanisms

- **Natural cooling** above 300 K.
- **Damage-driven heat amplification** when `tool_wear > 0.6` (and stronger above 0.85).
- **Hard clamps** on every field at the end of each tick.
- **`reset_inbound_buffers(machine_id)`** zeroes every `PROP_BUFFER` queue feeding into a maintained machine — without this, maintenance resets the machine state but the queued upstream disturbances re-inject the same pre-maintenance values within 3 ticks, snapping the machine straight back into Critical.

### Causal-delay buffers

```python
PROP_BUFFERS = {
    edge: deque([0.0] * delay, maxlen=delay)
    for edge, delay in PROPAGATION_DELAY.items()
}
```

Push-and-pop semantics: `_push_propagation(edge, value)` appends `value` and returns the *oldest* value in the deque. Combined with `maxlen`, this gives an exact `delay`-tick FIFO with no extra clock-keeping logic.

---

## 6. Backend Service (FastAPI)

**Location:** [`backend_fastapi/app/main.py`](backend_fastapi/app/main.py)

### Responsibilities (per WS tick)

1. Step the digital twin → 4 machine dicts.
2. Apply maintenance cooldown decay.
3. Run AI fusion via `machine_analyzer.analyze_machines()`.
4. Persist a `MachineLog` snapshot (SQLite).
5. **Periodically** (every 60 s) clean out `MachineLog` rows older than 30 minutes.
6. Compute `agent_alerts` (Warning + Critical) and POST to n8n (fire-and-forget).
7. Run the **dwell-rule auto-maintenance**: if a machine has been Critical for ≥ 10 s and is not in cooldown, drain any active what-if scenario (or run a standard reset), then emit STARTING + SUCCESS records.
8. Compute factory-level analytics (plant health score, most unstable machine, count needing attention).
9. Merge in-process `agent_actions` with the last 10 of `RECENT_AGENT_ACTIONS` (n8n-driven) and ship as the WS payload.

### Startup hooks

- **`_create_tables`** — calls `Base.metadata.create_all(engine)` and runs a tiny SQLite ALTER-TABLE migration to add the `is_whatif` column to a pre-existing `maintenance_logs` table (since `create_all` cannot alter).
- **`_warmup_llm_on_start`** — daemon thread that calls `warmup_llm()` so the first chatbot LLM query isn't extra-slow.

### UTF-8 stdout shim

The first 12 lines of `main.py` reconfigure `sys.stdout` and `sys.stderr` to UTF-8 with `errors="replace"` because Windows + Python 3.14 defaults to `cp1252`, and the codebase has many emoji `print()` calls that would otherwise propagate UnicodeEncodeError up through request handlers as 500s.

---

## 7. Closed-Loop n8n Agent Pipeline

### Workflow shape (`n8n/workflows/synaptic_fabric_agent.json`)

```
[Webhook /synfab-alert]
        │
        ▼
   [Normalize Alert]    ← strips machine_id / severity / risk into a flat shape
        │
        ▼
  [Switch on severity]
        │ ──── CRITICAL ──── ▶ [Ollama: Justify (phi3, cite root cause)]
        │                          │
        │                          ▼
        │                   [POST /agent/action]  → AUTO_MAINTENANCE
        │
        └──── WARNING ──── ▶ [POST /agent/action]  → NOTIFY_OPERATOR
                                   (skip LLM)
```

### Outbound from FastAPI

`backend_fastapi/app/n8n_client.py` — `send_alert(machine, severity, risk)`:

- Fire-and-forget `httpx.AsyncClient` POST to `http://localhost:5678/webhook/synfab-alert`.
- **Throttled per machine** (won't spam n8n if a machine sits in Critical for many ticks).
- **Swallows connection errors** — if n8n is down, the WS loop keeps running.

### Inbound to FastAPI

`backend_fastapi/app/agent_webhook.py` — `POST /agent/action` accepts:

```python
class AgentAction(BaseModel):
    machine_id: str
    action: str                    # "AUTO_MAINTENANCE" | "NOTIFY_OPERATOR"
    reason: Optional[str]
    justification: Optional[Any]   # passthrough from n8n's Ollama node
    source: Optional[str] = "n8n"
```

For `AUTO_MAINTENANCE`, the handler:

1. Checks if any what-if snapshot is active and either drains the entire scenario (logging `WHAT_IF_REVERT` for every restored machine) or applies the standard reset (`tool_wear *= 0.15`, `vibration *= 0.25`, `temperature -= 8`, `torque *= 0.92`).
2. Resets inbound propagation buffers.
3. Appends a record to in-memory `RECENT_AGENT_ACTIONS` (capped at 50).
4. Persists a `MaintenanceLog` row with `source="n8n"` (or whatever n8n reports), capturing the machine's `health_status` and `prediction` at the moment of the action.

### Failure modes

- **Ollama not pulled** → CRITICAL branch errors at the Ollama HTTP node; WARNING branch and corrective POST still work. Pull once with `docker exec synfab_ollama ollama pull phi3`.
- **n8n down** → `n8n_client.py` swallows; nothing else breaks.
- **`/agent/action` 500** → in-process auto-maintenance still fires via the dwell rule (10 s in Critical), so the system is corrective even with n8n disconnected.

---

## 8. Local Two-Tier Chatbot

### Routing

The dashboard chatbot's `/chat/stream` endpoint is a **deliberately n8n-free** path. It runs entirely in-process for two reasons:

- **Latency.** Routing through an n8n HTTP-hop on every keystroke would push median latency above 500 ms.
- **Determinism.** Most operator queries are metric lookups (`temperature of M_3`, `which is worst`), which deserve a fast-path lookup, not an LLM round-trip.

```
user query
   │
   ▼
[fast deterministic path]   ←── regex match against LIVE_MACHINES
   │  metric lookups, status, comparisons, plant health, alerts
   │  ~10–300 ms, NO LLM call
   ▼
[LLM reasoning path]        ←── triggered only when reasoning words appear
   (why / explain / how / should / cause / suggest / trend / history)
   - slim prompt (focused machine; history added only when explicitly asked)
   - Ollama params: num_predict=80, num_ctx=1024, num_thread=8
   - streamed back as text/plain, token by token (typing effect)
```

### Implementation

| Concern | File |
|---|---|
| Endpoint + tier router | [`backend_fastapi/app/chatbot_api.py`](backend_fastapi/app/chatbot_api.py) |
| Ollama HTTP client | [`backend_fastapi/chatbot/llm_client.py`](backend_fastapi/chatbot/llm_client.py) |
| RAG service (Qdrant) | [`backend_fastapi/chatbot/rag_service.py`](backend_fastapi/chatbot/rag_service.py) |
| History tools | `backend_fastapi/chatbot/history_tools.py` |
| Streaming consumer + Stop button | [`frontend_dashboard/src/components/Chatbot.js`](frontend_dashboard/src/components/Chatbot.js) |

The legacy `/chat` endpoint is preserved as a non-streaming fallback that shares the same fast/LLM routing.

---

## 9. Maintenance Logging & Audit Trail

### Schema

```python
class MaintenanceLog(Base):
    __tablename__ = "maintenance_logs"
    id            = Column(Integer, primary_key=True)
    timestamp     = Column(DateTime, default=datetime.utcnow, index=True)
    machine_id    = Column(String, index=True)
    action        = Column(String)   # MANUAL | AUTO | WHAT_IF_SPIKE | WHAT_IF_REVERT
    status        = Column(String)   # STARTING | SUCCESS | APPLIED | IGNORED
    source        = Column(String)   # dashboard | dwell_rule | n8n | dashboard_whatif
    reason        = Column(Text, nullable=True)
    health_status = Column(String, nullable=True)
    risk          = Column(Float, nullable=True)
    is_whatif     = Column(Boolean, default=False, nullable=False)
```

### Persistence sites

- `manual_maintenance` (dashboard button) — one `APPLIED` row + STARTING/SUCCESS WS records.
- Dwell-rule auto-maintenance — STARTING + SUCCESS rows.
- `agent_action` from n8n — one `APPLIED` row.
- `inject_spike` — one `WHAT_IF_SPIKE` row per affected machine (origin + chain neighbours).
- Any maintenance during an active what-if — one `WHAT_IF_REVERT` row per restored machine.

### Endpoints

| Method · Path | Returns | Filters |
|---|---|---|
| `GET /maintenance/logs` | Newest-first JSON list | `minutes`, `machine_id`, `limit` (≤ 10000) |
| `GET /maintenance/logs/download` | File download | `format=csv\|json`, `minutes`, `machine_id` |

CSV columns: `id, timestamp_utc, machine_id, action, status, source, is_whatif, health_status, risk, reason`.

### Path-conflict gotcha

`/maintenance/logs` clashes with `POST /maintenance/{machine_id}` — FastAPI matches `/maintenance/logs` against `{machine_id}=logs` and returns 405 if methods differ. The download endpoint at `/maintenance/logs/download` has an extra path segment, so it doesn't conflict. The list endpoint avoids the conflict because it's `GET` while the manual-maintenance route is `POST` with a single segment under it — FastAPI's method-based routing disambiguates here, but if a `GET /maintenance/{machine_id}` were ever added it would shadow the list endpoint.

---

## 10. What-If Spike Scenarios

Operators can hypothetically perturb any machine's state to visualize blast-radius effects, fully reversible by any subsequent maintenance action.

### Endpoint

```http
POST /spike/{machine_id}
Content-Type: application/json

{ "temperature": 318, "vibration_index": 0.95,
  "tool_wear": 0.92, "torque": null, "note": "..." }
```

### Mechanism

1. Compute `delta` for each provided field, relative to the *current* state of the origin machine.
2. For every machine in the chain (`M_1`–`M_4`), look up an attenuation factor by signed chain-distance:

   | Distance | -3 | -2 | -1 | 0 (origin) | +1 | +2 | +3 |
   |---|---|---|---|---|---|---|---|
   | Attenuation | 0.05 | 0.10 | 0.20 | **1.00** | 0.60 | 0.40 | 0.25 |

3. Snapshot each machine's current state into `state.WHATIF_SNAPSHOTS[mid]` (only if not already snapshotted — preserves the *original* baseline if multiple sequential spikes occur).
4. Apply `delta * attenuation` to each machine's chosen fields, with per-field clamping.
5. Record one `WHAT_IF_SPIKE` log row per affected machine, with `is_whatif=True`.
6. Return the affected list:

   ```json
   {
     "status": "success",
     "origin": "M_2",
     "affected": [
       {"machine_id":"M_1","attenuation":0.2,"is_origin":false,"applied":{...}},
       {"machine_id":"M_2","attenuation":1.0,"is_origin":true,"applied":{...}},
       {"machine_id":"M_3","attenuation":0.6,"is_origin":false,"applied":{...}},
       {"machine_id":"M_4","attenuation":0.4,"is_origin":false,"applied":{...}}
     ],
     "hint": "Performing maintenance on ANY machine in this scenario will revert the whole plant to its pre-spike state."
   }
   ```

### Empirical trace (spike `M_2` with `vibration=0.95, tool_wear=0.92`)

| Machine | Attenuation | Δ vib | Δ wear | Δ temp | Health after spike |
|---|---|---|---|---|---|
| M_1 | 0.2 | +0.090 | +0.167 | -0.03 | Healthy (mild reflection) |
| **M_2** | **1.0** | +0.324 | +0.812 | +2.21 | **Critical** (origin) |
| **M_3** | 0.6 | +0.554 | +0.495 | +2.20 | **Critical** (chain effect) |
| M_4 | 0.4 | +0.184 | +0.327 | +0.37 | Healthy |

A single failure visibly drags M_3 into Critical and adds measurable load to M_1 and M_4 — exactly the failure-cascade visualization operators need.

### Group revert

Maintenance on **any** machine in an active scenario triggers a full revert:

```json
{ "status":"success", "machine_id":"M_2", "reverted_whatif":true,
  "co_reverted":["M_1","M_3","M_4"] }
```

All four maintenance paths share the same drain-the-scenario logic:

1. Manual dashboard button.
2. Dwell-rule auto-maintenance.
3. n8n `POST /agent/action`.
4. (Implicit) — even if the maintained machine isn't the spike origin, the entire active scenario is restored.

---

## 11. Auto-Maintenance Logic

### Dwell rule

```python
CRITICAL_DWELL_SECONDS = 10
MACHINE_CRITICAL_SINCE = {}      # machine_id → wall-clock time entered Critical
MAINTENANCE_COOLDOWN  = {}       # machine_id → time of last reset
COOLDOWN_TIME = 20
```

A machine triggers auto-maintenance when *all three* hold:

1. `health_status == "Critical"` for the current tick.
2. It has been continuously Critical for ≥ `CRITICAL_DWELL_SECONDS` (10 s).
3. It is not within the `COOLDOWN_TIME` window (20 s) since its last reset.

Why a dwell rule (instead of a metric threshold)? Because real-world high-risk machines often have *individual* signals (e.g. `tool_wear`) that stay below their physics-override thresholds, but the **fused prediction** stays in Critical territory. Dwell-time gives a uniform "this machine has been bad long enough — service it" criterion that doesn't depend on which signal is the loudest right now.

### Effects

| Trigger | What happens to MACHINE_MEMORY |
|---|---|
| Manual maintenance (button) | `tool_wear *= 0.15`, `vibration *= 0.25`, `temperature -= 8` (floor 295), `torque *= 0.92` |
| Dwell-rule auto-maintenance | `tool_wear *= 0.15`, `vibration *= 0.25`, `temperature -= 10`, `torque *= 0.9` (slightly stronger than manual) |
| n8n `AUTO_MAINTENANCE` callback | Same as manual (`* 0.15`, `* 0.25`, `-8`, `* 0.92`) |
| **Any of the above during what-if** | Snapshot from `WHATIF_SNAPSHOTS[mid]` is restored verbatim |

In all cases `reset_inbound_buffers(mid)` is called to flush stale upstream queue entries.

### WS popup contract

The frontend `useMachineStream` hook watches the `agent_actions` field of the WS payload and de-duplicates by `${machine_id}-${timestamp}-${status}-${action}`. The popup queue serializes messages with a 3-second display each:

| Action | STARTING | SUCCESS |
|---|---|---|
| `AUTO_MAINTENANCE` | `⚙️ Performing maintenance on M_x` | `✅ Maintenance completed for M_x` |
| `MANUAL_MAINTENANCE` | same | same |
| `WHAT_IF_REVERT` | `↩️ Reverting what-if scenario on M_x` | `✅ M_x restored to pre-spike state` |

(Emoji glyphs are intentional in the popup queue messages — the user-facing text stays minimal but distinguishable.)

---

## 12. Frontend Dashboard

### Tech stack

- **React** via `create-react-app`.
- **`@react-three/fiber` + `drei`** for the 3D digital twin.
- **`recharts`** for the temperature line chart.
- **Inter** (UI text) + **JetBrains Mono** (numerical metrics) loaded via Google Fonts in `public/index.html`.

### Layout (top to bottom)

1. **Header** — eyebrow `SYNAPTIC FABRIC`, title `Mission Control`, subtitle line; bottom border.
2. **3D Digital Twin** — four named machine geometries on a chain-shaped plinth.
3. **Machine Card grid** — one card per machine.
4. **Factory Intelligence** — plant health %, most unstable machine, total machines, needs-attention list. Each as a flat stat card with a monospaced numeric value.
5. **Agent Alerts** — borderless rows with thin colored left-edge accents (amber for Warning, red for Critical) and a tinted background.
6. **Recent Maintenance Activity** *(collapsible, closed by default)* — auto-refreshes every 5 s via `GET /maintenance/logs?minutes=10&limit=200`. Sticky-header table with `max-height: 220px`, vertical scrollbar, what-if rows tinted amber with a `WHAT-IF` badge.
7. **Maintenance Log Downloads** *(collapsible)* — CSV / JSON export buttons.
8. **Live Temperature** *(collapsible)* — recharts line chart with a 1/5/10-min window selector.
9. **AI Assistant** — fixed bottom-right pill button; opens a 340 × 440 chat popup.
10. **Auto-maintenance popup** — fixed top-center 3-second toast queue.

### Machine Card composition

```
┌────────────────────────────────────────────────────┐
│ M_3                                  [HEALTHY · ●] │
│ CNC Milling Tool                                   │
│ Surface finishing                                  │
├────────────────────────────────────────────────────┤
│ ┌──────────────────┬──────────────────┐            │
│ │ TEMP             │ TORQUE           │            │
│ │ 296.06 K         │ 44.18 Nm         │            │
│ ├──────────────────┼──────────────────┤            │
│ │ WEAR             │ VIBRATION        │            │
│ │ 10.2%            │ 0.153            │            │
│ └──────────────────┴──────────────────┘            │
│                                                    │
│ FAILURE RISK                            12%        │
│ ▓▓░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░         │
│                                                    │
│ ┌──────────────────┬──────────────────┐            │
│ │ RUL CYCLES       │ EST. TIME        │            │
│ │ 280              │ 5.6 hrs          │            │
│ └──────────────────┴──────────────────┘            │
│                                                    │
│ [   Perform Maintenance   ]                        │
│ [    Inject Spike (◊)     ]                        │
│                                                    │
│ INSPECTION                                         │
│ No issues detected.                                │
└────────────────────────────────────────────────────┘
```

### `useMachineStream` hook

[`frontend_dashboard/src/useMachineStream.js`](frontend_dashboard/src/useMachineStream.js) handles:

- WebSocket connection to `ws://127.0.0.1:8000/ws/machines`.
- Auto-reconnect with 2 s backoff on close.
- A popup queue with de-duplication (`shownActionsRef.current` Set).
- Mapping the raw WS payload into the shape the rest of the app expects.

### Design system

- Single-color background `#050810` (no radial gradient) so cards read as foreground.
- Stat values use **JetBrains Mono** with `font-feature-settings: "tnum", "zero"` for tabular alignment and unambiguous zeros.
- Thin 1 px borders (`rgba(148, 163, 184, 0.10)`) instead of heavy box-shadows.
- Status pills are dot-prefixed labels with thin matching borders — Healthy = emerald (`#34d399`), Warning = amber (`#fbbf24`), Critical = coral (`#f87171`).
- Custom thin scrollbars (`*::-webkit-scrollbar { width: 8px }`) globally, using `rgba(148, 163, 184, 0.25)` on the thumb.
- All emojis stripped from user-facing surfaces (replaced with typographic emphasis: weight, color, letter-spacing); emojis remain only inside the auto-maintenance popup queue text strings.

---

## 13. Data Model & Persistence

### Engine

SQLite at `./machine_data.db` with `check_same_thread=False` for FastAPI's threaded request handling.

### Tables

| Table | Purpose | Lifetime |
|---|---|---|
| `machine_logs` | Per-tick metric snapshot of every machine | Cleaned every 60 s — rows older than 30 minutes are deleted |
| `maintenance_logs` | Every maintenance / spike / revert event | Permanent (until explicit purge) |

### Migrations

Alembic is **not** wired in (intentionally — this is a demo platform, not a production migration story). Instead:

1. `Base.metadata.create_all(engine)` runs on FastAPI startup to create any missing tables.
2. A bespoke SQLite ALTER-TABLE migration runs immediately after `create_all` to add the `is_whatif` column to a pre-existing `maintenance_logs` table (because `create_all` cannot alter existing tables and the column was added later).

Future schema changes that aren't pure additions would need either a manual DROP/recreate or an Alembic adoption.

### Why SQLite (not PostgreSQL)

The architecture brief mentions PostgreSQL but this build uses SQLite because:

- Zero infrastructure footprint matters for a local-only demo.
- Write-rate (~4 rows/sec to `machine_logs`, plus occasional `maintenance_logs` writes) is well under SQLite's ceiling.
- The cleanup job keeps `machine_logs` capped at ~30 minutes ≈ 7,200 rows, which SQLite handles without breathing hard.

---

## 14. Deployment & Local Setup

### Prerequisites

- Windows / macOS / Linux with Docker Desktop or compatible
- Python 3.11+ (this build runs on 3.14 with the UTF-8 stdout shim)
- Node 18+

### Startup sequence

```bash
# 1. Local infrastructure
docker compose up -d n8n qdrant ollama
docker exec -it synfab_ollama ollama pull phi3        # CRITICAL branch
docker exec -it synfab_ollama ollama pull phi3:mini   # dashboard chat

# 2. Backend (host)
./venv/Scripts/python.exe -m uvicorn backend_fastapi.app.main:app \
  --host 0.0.0.0 --port 8000

# 3. Frontend (host)
cd frontend_dashboard && npm start

# 4. Activate the n8n workflow (one-time, in the n8n UI)
#    Open http://localhost:5678 → Create owner account → Import
#    n8n/workflows/synaptic_fabric_agent.json → Activate.
```

### Default ports

| Service | URL |
|---|---|
| FastAPI | http://localhost:8000 |
| React dashboard | http://localhost:3000 |
| n8n | http://localhost:5678 |
| Qdrant | http://localhost:6333 |
| Ollama | http://localhost:11434 |

### Smoke-test commands

```bash
# Manual maintenance on M_3
curl -X POST http://localhost:8000/maintenance/M_3

# Inject a what-if spike with chain propagation
curl -X POST http://localhost:8000/spike/M_2 \
  -H "Content-Type: application/json" \
  -d '{"vibration_index":0.95,"tool_wear":0.92}'

# Trigger n8n via its production webhook
curl -X POST http://localhost:5678/webhook/synfab-alert \
  -H "Content-Type: application/json" \
  -d '{"machine_id":"M_3","severity":"CRITICAL","prediction":0.92}'

# Pull the last 10 minutes of maintenance log
curl 'http://localhost:8000/maintenance/logs?minutes=10' | jq .
```

---

## 15. Operational Gotchas

### Windows + Python 3.14: UTF-8 stdout

The codebase has many emoji `print()` calls that crash on `cp1252`. The fix lives at the very top of `main.py`:

```python
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
```

If you ever add a new entrypoint, replicate this block — otherwise the first emoji `print()` will trip `UnicodeEncodeError` and surface as a 500 from a request handler.

### Docker Desktop's path-with-space bug

If your Windows username contains a space (e.g. `SIDDHI KARHEKAR`), Docker Desktop's Inference Manager and Secrets Engine will fail to bind their Unix sockets at `%LOCALAPPDATA%\Docker\run\dockerInference` and `%LOCALAPPDATA%\docker-secrets-engine\engine.sock` because `unix://` URLs split on the space. Symptom: a startup dialog with "An unexpected error occurred · Docker Desktop encountered an unexpected error and needs to close · The filename, directory name, or volume label syntax is incorrect."

**Workaround that worked:**

1. Kill all Docker processes: `taskkill /F /IM "Docker Desktop.exe"` and `taskkill /F /IM "com.docker.backend.exe"`.
2. Shut down WSL: `wsl --shutdown`.
3. Rename the broken IPC dirs (the zombie pipe handles can't be deleted, only renamed) **using Python's `os.rename`** — Windows' `cmd /c ren` and `rmdir` both fail with `ERROR_INVALID_NAME (123)`:

   ```python
   import os, time
   ts = int(time.time())
   for src in [
       r'C:\Users\NAME WITH SPACE\AppData\Local\Docker\run',
       r'C:\Users\NAME WITH SPACE\AppData\Local\docker-secrets-engine',
   ]:
       os.rename(src, f"{src}_broken_{ts}")
   ```

4. Relaunch Docker Desktop. It creates fresh `run/` and `docker-secrets-engine/` directories and starts cleanly.

The renamed `*_broken_*` directories are harmless on disk; they release after a Windows reboot.

### Soft-failure modes

- **n8n down** → `n8n_client.py` swallows; WS keeps streaming.
- **Ollama not pulled** → CRITICAL n8n branch errors at the Ollama node; dashboard chatbot drops to fast deterministic path; everything else keeps working.
- **`gnn.pth` corrupt or missing** → `gnn_inference.py` no longer loads it at all; the chain-aware physics fallback is the canonical path.
- **WebSocket disconnect** → frontend's `useMachineStream` reconnects with 2 s backoff.

---

## 16. Endpoint Reference

| Method | Path | Purpose |
|---|---|---|
| `WS` | `/ws/machines` | Live stream — machines, analytics, alerts, actions (~1 Hz) |
| `GET` | `/history?minutes=N` | Per-machine temperature history (1 ≤ N ≤ 60) |
| `POST` | `/maintenance/{machine_id}` | Manual maintenance — drains active what-if scenario or runs standard reset |
| `POST` | `/spike/{machine_id}` | Inject a what-if spike with chain propagation |
| `POST` | `/agent/action` | Closed-loop hook called by n8n |
| `GET` | `/agent/actions?limit=N` | In-memory recent agent actions (n8n-driven) |
| `GET` | `/agent/health` | `{ "status": "ok", "live_machines": [...] }` |
| `GET` | `/maintenance/logs` | DB-backed list with `minutes`, `machine_id`, `limit` filters |
| `GET` | `/maintenance/logs/download` | CSV or JSON file download |
| `POST` | `/chat` | Two-tier chat (non-streaming) |
| `POST` | `/chat/stream` | Two-tier chat (`text/plain` streamed) |

---

## 17. WebSocket Payload Reference

```jsonc
{
  "machines": [
    {
      "machine_id": "M_3",
      "temperature": 296.06,
      "torque": 44.18,
      "tool_wear": 0.1024,
      "vibration_index": 0.1531,

      "pinn_temperature": 275.485,    // PINN heat-eq prediction
      "pinn_risk": 0.0,
      "gnn_risk": 0.21,               // chain-aware physics fallback
      "anomaly_score": 0.063,
      "anomaly_ml_score": 0.05,
      "failure_probability": 0.121,
      "prediction": 0.121,            // fused final risk

      "rul_cycles": 280,
      "rul_time": "5.6 hrs",
      "future_temperature": 297.31,

      "health_status": "Healthy",
      "root_cause": [...],            // analyzer rule output
      "alerts": [
        { "level": "WARNING", "message": "High temperature" }
      ],
      "shap": { "tool_wear": 0.31, "temperature": 0.18, ... },
      "ai_explanation": "Healthy | anomaly=0.063 | risk=0.121 | gnn=0.21",
      "ai_reason": "Primary factor: tool_wear"
    }
    /* …M_1..M_4 */
  ],
  "factory_analytics": {
    "plant_health_score": 88.2,
    "most_unstable_machine": "M_4",
    "total_machines": 4,
    "machines_needing_attention": []
  },
  "agent_alerts":  [
    { "machine_id": "M_3", "level": "CRITICAL", "message": "Failure risk 92%" }
  ],
  "agent_actions": [
    { "machine_id": "M_3", "action": "AUTO_MAINTENANCE",
      "status": "STARTING", "timestamp": 1778064686.1494906 },
    { "machine_id": "M_3", "action": "AUTO_MAINTENANCE",
      "status": "SUCCESS",  "timestamp": 1778064686.1504905 }
  ]
}
```

---

## 18. Tuning History (What Changed and Why)

This section documents the most consequential tuning decisions made during development, so future contributors don't undo them inadvertently.

### M_3-stuck-in-Critical fix

**Symptom:** M_3 (CNC Milling Tool) was perpetually in Warning/Critical, snapping back into Critical seconds after any maintenance.

**Root causes (all real, all fixed):**

1. **GNN saturation.** The pretrained `gnn.pth` produced near-constant 1.0 logits → 0.15 floor on every fused prediction. → Replaced with chain-aware physics fallback (see §4.2).
2. **Simulator over-coupling.** M_3 vibration update was `V_new = 0.98·V_old + 0.6·delayed_vib`, steady-state amplification `0.6/(1 - 0.98) = 30×`. → Tightened to `0.94·V_old + 0.18·delayed_vib`, steady-state `3×`. Heat injection from upstream vib `* 0.4 → * 0.15`. Wear coupling `* 0.0025 → * 0.0010`.
3. **M_2 monotonic drift.** M_2 vibration update had no decay term, so it climbed without bound → pinned M_3. → Added `* 0.985` self-decay.
4. **Stale propagation buffers.** Maintenance reset state but `M_2→M_3` queue still held the pre-maintenance high values → M_3 re-entered Critical within 3 ticks. → Added `reset_inbound_buffers(mid)` to all maintenance paths.
5. **GNN weighting.** Original adjacency had `adj[i+1][i] = 1.0` (upstream) and `adj[i][i] = 1.0` (self) → after row normalization, M_3 weighted upstream equally with itself. → Reduced upstream edge to `0.5`, reverse to `0.15`.

### Empirical verification (post-fix)

| Phase | M_3 Critical ticks | M_3 max vib | M_3 max pred |
|---|---|---|---|
| 60 s warm-up (no maintenance) | **0** | 0.738 | 0.700 |
| 30 s after M_3 maintenance | **0** | 0.134 | 0.216 |
| 30 s after maintenance, with M_2 spiking to vib=0.915 | **0** | 0.506 | 0.205 |

### Maintenance popup wiring

**Symptom:** Clicking "Perform Maintenance" on a card showed no popup.

**Cause:** Manual maintenance only wrote to the DB, never to `agent_actions` (which the WS payload exposes and the popup hook watches).

**Fix:** `manual_maintenance` now appends STARTING + SUCCESS records into `RECENT_AGENT_ACTIONS` (timestamp offset by `+0.001 s` to keep them distinct in the dedup set). The frontend popup matcher was simultaneously broadened from a single-action match (`AUTO_MAINTENANCE`) to a tuple matcher covering `AUTO_MAINTENANCE`, `MANUAL_MAINTENANCE`, and `WHAT_IF_REVERT`.

### Schema compatibility

When the `is_whatif` column was added, the pre-existing `maintenance_logs` table broke `INSERT`s with `OperationalError: table maintenance_logs has no column named is_whatif`. **Fix:** lightweight ALTER-TABLE migration on FastAPI startup that introspects `PRAGMA table_info(maintenance_logs)` and adds the column only if missing.

---

## 19. Repository Structure

```
SynapticFabricfinal/
├── backend_fastapi/
│   ├── ai_engine/
│   │   ├── machine_analyzer.py     # GNN + PINN + ML + anomaly fusion + alerts + RUL
│   │   └── root_cause.py           # Per-machine root-cause rules
│   ├── analytics/
│   │   └── factory_analytics.py    # Plant-level metrics
│   ├── app/
│   │   ├── main.py                 # FastAPI entrypoint, WS, /history, /maintenance, /spike
│   │   ├── agent_webhook.py        # /agent/action, /agent/actions, /agent/health,
│   │   │                           # /maintenance/logs, /maintenance/logs/download
│   │   ├── chatbot_api.py          # /chat + /chat/stream (two-tier router)
│   │   ├── n8n_client.py           # Outbound alerts to n8n (throttled, fire-and-forget)
│   │   └── state.py                # LIVE_MACHINES + WHATIF_SNAPSHOTS
│   ├── chatbot/
│   │   ├── llm_client.py           # Ollama HTTP client + warmup
│   │   ├── rag_service.py          # Qdrant retrieval
│   │   └── history_tools.py        # Conversation memory
│   └── database/
│       ├── database.py             # SQLAlchemy engine + session
│       ├── models.py               # MachineLog, MaintenanceLog
│       └── maintenance_log.py      # record_maintenance() helper
│
├── digital_twin/
│   └── simulator.py                # 4-node causal-physics simulator (M_1..M_4)
│
├── ml_models/
│   ├── graph_builder.py            # Chain-encoded adjacency
│   ├── gnn_model.py                # SimpleGNN (Linear over message pass)
│   ├── gnn_inference.py            # Chain-aware physics fallback (replaces saturating ckpt)
│   ├── failure_model.py            # ML failure probability
│   ├── anomaly_model.py            # ML anomaly score
│   ├── transformer_inference.py    # Short-horizon temperature forecast
│   └── explainer.py                # SHAP attributions
│
├── pinn_model/
│   ├── heat_pinn.py                # Physics-informed network (heat-eq residual loss)
│   └── pinn_inference.py           # predict_temp(temp, torque, air)
│
├── frontend_dashboard/
│   ├── public/index.html           # Inter + JetBrains Mono fonts, custom scrollbars
│   └── src/
│       ├── App.js                  # Mission Control dashboard
│       ├── useMachineStream.js     # WS client + popup queue
│       ├── components/
│       │   ├── MachineCard.js / .css   # Industrial card with 2x2 metric grid + spike form
│       │   ├── FactoryTwin3D.js        # 3D twin
│       │   ├── TemperatureChart.js     # recharts line chart
│       │   ├── AlertPanel.js
│       │   └── Chatbot.js
│       └── utils/machineInfo.js    # name + process for M_1..M_4
│
├── n8n/
│   ├── workflows/synaptic_fabric_agent.json
│   └── README.md
│
├── docker-compose.yml              # n8n + Qdrant + Ollama
├── machine_data.db                 # local SQLite (gitignored)
├── CLAUDE.md                       # Repo-internal architecture notes
└── PROJECT_REPORT.md               # this file
```

---

## 20. Future Work & Known Limitations

### Future work

- **Persist `WHATIF_SNAPSHOTS` across restarts.** Today they live only in process memory — a backend restart during an active scenario means snapshots are lost and machines can't be reverted to original. A small SQLite table keyed on `machine_id` would solve this.
- **Retrain the GNN.** The current chain-aware fallback is physics-correct but linear. A properly normalized + retrained `gnn.pth` (with feature standardization in `graph_builder.py`) could capture nonlinear chain interactions the fallback misses.
- **Alembic migrations.** Replace the bespoke ALTER-TABLE startup hook with a real migration story before adding any non-additive schema changes.
- **PostgreSQL adapter.** Wire it in (it's mentioned in the architecture brief). The DB access is already through SQLAlchemy `Session`, so the engine swap is configuration.
- **Production-grade n8n auth.** The current setup uses a single owner account; for any multi-user deployment the workflow should run under an API-key-gated execution context.
- **Per-tenant config.** All thresholds (`CRITICAL_DWELL_SECONDS`, `COOLDOWN_TIME`, `ALERT_THRESHOLD`, fusion weights) are hardcoded in `main.py` and `machine_analyzer.py`. A YAML config + reload endpoint would make this tunable without redeploys.

### Known limitations

- **Single-process simulator.** `MACHINE_MEMORY` and `WHATIF_SNAPSHOTS` are module-level state. Horizontal scaling would need an external state store (Redis would be the natural fit).
- **No plant-wide spike test scenarios.** What-ifs are anchored on a single origin machine; multi-origin scenarios (e.g. simultaneous M_1 and M_3 failure) require sequential spikes which compound deltas in a way that may not match a true coincident-failure profile.
- **Fixed chain topology.** The simulator and GNN assume a 4-node linear chain. A branching or recirculating topology would need rewrites in `simulator.py`, `graph_builder.py`, and `_chain_targets()` in `main.py`.
- **No authentication.** The dashboard, FastAPI endpoints, and n8n owner account are all open on localhost — fine for local demo, not for any networked deployment.

---

*Last updated 2026-05-06 by the development team.*
