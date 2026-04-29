import sys

# ------------------------------------------------------------
# Force UTF-8 stdout/stderr on Windows so the many emoji
# print() calls scattered through the codebase don't trip
# cp1252 and bubble up as 500s from request handlers.
# ------------------------------------------------------------
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from fastapi import FastAPI, WebSocket, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import asyncio
import time
from datetime import datetime, timedelta

from digital_twin.simulator import run_digital_twin, MACHINE_MEMORY
from backend_fastapi.ai_engine.machine_analyzer import machine_analyzer
from backend_fastapi.app.chatbot_api import router as chatbot_router
from backend_fastapi.app.agent_webhook import router as agent_router, RECENT_AGENT_ACTIONS
from backend_fastapi.app.n8n_client import send_alert as n8n_send_alert
from backend_fastapi.database.database import SessionLocal, get_db
from backend_fastapi.database.models import MachineLog
from backend_fastapi.chatbot.rag_service import build_context_from_db
from backend_fastapi.chatbot.llm_client import warmup as warmup_llm
from backend_fastapi.app.state import LIVE_MACHINES


app = FastAPI()


@app.on_event("startup")
def _warmup_llm_on_start():
    # Load phi3 into memory in a background thread so first chat is snappy.
    import threading
    threading.Thread(target=warmup_llm, daemon=True).start()

# ==========================================
# 🌐 CORS
# ==========================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chatbot_router)
app.include_router(agent_router)

# ==========================================
# 🔧 CONFIG
# ==========================================
MAINTENANCE_COOLDOWN = {}
COOLDOWN_TIME = 20

# How long a machine must remain in Critical before auto-maintenance fires.
CRITICAL_DWELL_SECONDS = 10
# Tracks the wall-clock time each machine first entered Critical state.
MACHINE_CRITICAL_SINCE = {}

ALERT_THRESHOLD = 0.4

LAST_CLEANUP = 0


# ==========================================
# 💾 SAVE MACHINE SNAPSHOT
# ==========================================
def save_machine_snapshot(machines):

    db = SessionLocal()

    try:
        for m in machines:
            log = MachineLog(
                machine_id=m.get("machine_id"),
                temperature=m.get("temperature"),
                torque=m.get("torque"),
                tool_wear=m.get("tool_wear"),
                vibration_index=m.get("vibration_index"),
                anomaly_score=m.get("anomaly_score", 0),
                health_status=m.get("health_status"),
                failure_probability=m.get("prediction", 0)
            )
            db.add(log)

        db.commit()

    except Exception as e:
        print("❌ DB SAVE ERROR:", e)

    finally:
        db.close()


# ==========================================
# 🧹 CLEAN OLD DATA
# ==========================================
def cleanup_old_data():

    db = SessionLocal()

    try:
        cutoff = datetime.utcnow() - timedelta(minutes=30)

        deleted = db.query(MachineLog).filter(
            MachineLog.timestamp < cutoff
        ).delete()

        db.commit()

        print(f"🧹 Cleaned {deleted} old records")

    except Exception as e:
        print("❌ CLEANUP ERROR:", e)

    finally:
        db.close()


# ==========================================
# 📈 HISTORY API (FIXED)
# ==========================================
@app.get("/history")
def get_history(minutes: int = Query(5, ge=1, le=60)):

    db = SessionLocal()

    try:
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)

        records = db.query(MachineLog).filter(
            MachineLog.timestamp >= cutoff
        ).all()

        grouped = {}

        for r in records:
            ts = r.timestamp.strftime("%H:%M:%S")

            if ts not in grouped:
                grouped[ts] = {
                    "time": ts,
                    "M_1": None,
                    "M_2": None,
                    "M_3": None,
                    "M_4": None,
                }

            grouped[ts][r.machine_id] = r.temperature

        result = list(grouped.values())

        print(f"📊 HISTORY RETURNED: {len(result)} rows")

        return result

    except Exception as e:
        print("❌ HISTORY ERROR:", e)
        return []

    finally:
        db.close()


# ==========================================
# 🔧 MANUAL MAINTENANCE ENDPOINT
# ==========================================
@app.post("/maintenance/{machine_id}")
def manual_maintenance(machine_id: str):
    if machine_id not in MACHINE_MEMORY:
        return {"status": "error", "message": "unknown machine"}

    s = MACHINE_MEMORY[machine_id]
    s["tool_wear"] *= 0.15
    s["vibration_index"] *= 0.25
    s["temperature"] = max(s["temperature"] - 8, 295)
    s["torque"] *= 0.92

    MAINTENANCE_COOLDOWN[machine_id] = time.time()

    return {"status": "success", "machine_id": machine_id}


# ==========================================
# 🌐 WEBSOCKET STREAM
# ==========================================
@app.websocket("/ws/machines")
async def stream(ws: WebSocket):

    await ws.accept()
    print("✅ WebSocket connected")

    global LAST_CLEANUP

    try:
        while True:

            # 🔵 DIGITAL TWIN
            machines = run_digital_twin()

            # 🔧 COOLDOWN
            for m in machines:
                mid = m["machine_id"]

                if mid in MAINTENANCE_COOLDOWN:
                    elapsed = time.time() - MAINTENANCE_COOLDOWN[mid]

                    if elapsed >= COOLDOWN_TIME:
                        del MAINTENANCE_COOLDOWN[mid]

            # 🤖 AI ANALYSIS
            analyzed = machine_analyzer.analyze_machines(machines)

            for m in analyzed:
                LIVE_MACHINES[m["machine_id"]] = m

            save_machine_snapshot(analyzed)

            # 🧹 CLEANUP
            if time.time() - LAST_CLEANUP > 60:
                cleanup_old_data()
                LAST_CLEANUP = time.time()

            # 🤖 AGENT LOGIC
            agent_alerts = []
            agent_actions = []

            for m in analyzed:
                mid = m["machine_id"]

                # ✅ FIXED: use ONLY prediction
                risk = m.get("prediction", 0)

                # ALERTS
                if risk > ALERT_THRESHOLD:
                    severity = "CRITICAL" if risk > 0.7 else "WARNING"

                    agent_alerts.append({
                        "machine_id": mid,
                        "level": severity,
                        "message": f"Failure risk {round(risk*100)}%"
                    })

                    # 🔔 push to n8n agent pipeline (best-effort)
                    try:
                        asyncio.create_task(
                            n8n_send_alert(m, severity, risk)
                        )
                    except Exception as _e:
                        pass

                
                
                # ==========================================
                # 🔧 AUTO-MAINTENANCE (Critical + dwell time)
                # ==========================================
                # Track when this machine entered/left Critical
                if m.get("health_status") == "Critical":
                    if mid not in MACHINE_CRITICAL_SINCE:
                        MACHINE_CRITICAL_SINCE[mid] = time.time()
                else:
                    MACHINE_CRITICAL_SINCE.pop(mid, None)

                # Trigger if it has been Critical long enough and no cooldown
                if (
                    m.get("health_status") == "Critical"
                    and mid in MACHINE_CRITICAL_SINCE
                    and time.time() - MACHINE_CRITICAL_SINCE[mid] >= CRITICAL_DWELL_SECONDS
                    and mid not in MAINTENANCE_COOLDOWN
                ):

                    agent_actions.append({
                        "machine_id": mid,
                        "action": "AUTO_MAINTENANCE",
                        "status": "STARTING",
                        "timestamp": time.time()
                    })

                    await asyncio.sleep(1.5)

                    # 🔥 STRONG RESET (ENSURE REAL RECOVERY)
                    MACHINE_MEMORY[mid]["tool_wear"] *= 0.15
                    MACHINE_MEMORY[mid]["vibration_index"] *= 0.25
                    MACHINE_MEMORY[mid]["temperature"] -= 10
                    MACHINE_MEMORY[mid]["torque"] *= 0.9

                    MAINTENANCE_COOLDOWN[mid] = time.time()
                    MACHINE_CRITICAL_SINCE.pop(mid, None)

                    agent_actions.append({
                        "machine_id": mid,
                        "action": "AUTO_MAINTENANCE",
                        "status": "SUCCESS",
                        "timestamp": time.time()
                    })

            # ==========================================
            # 📊 ANALYTICS (FIXED)
            # ==========================================
            risks = [m.get("prediction", 0) for m in analyzed]

            avg_risk = sum(risks) / len(risks) if risks else 0

            unstable = max(
                analyzed,
                key=lambda x: x.get("prediction", 0)
            )

            analytics = {
                "plant_health_score": round((1 - avg_risk) * 100, 1),
                "most_unstable_machine": unstable["machine_id"],
                "total_machines": len(analyzed),
                "machines_needing_attention": [
                    m["machine_id"]
                    for m in analyzed
                    if m.get("health_status") != "Healthy"
                ]
            }

            # merge n8n-driven actions (closed-loop) into WS payload
            n8n_actions = list(RECENT_AGENT_ACTIONS[-10:])

            await ws.send_json({
                "machines": analyzed,
                "factory_analytics": analytics,
                "agent_alerts": agent_alerts,
                "agent_actions": agent_actions + n8n_actions
            })

            await asyncio.sleep(1)

    except Exception as e:
        print("❌ WebSocket error:", e)

    finally:
        print("🔌 WebSocket closed")