from fastapi import FastAPI, WebSocket, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import asyncio
import time
from datetime import datetime, timedelta

from digital_twin.simulator import run_digital_twin, MACHINE_MEMORY
from backend_fastapi.ai_engine.machine_analyzer import machine_analyzer
from backend_fastapi.app.chatbot_api import router as chatbot_router
from backend_fastapi.database.database import SessionLocal, get_db
from backend_fastapi.database.models import MachineLog
from backend_fastapi.chatbot.rag_service import build_context_from_db
from backend_fastapi.app.state import LIVE_MACHINES


app = FastAPI()

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

# ==========================================
# 🔧 CONFIG
# ==========================================
MAINTENANCE_COOLDOWN = {}
COOLDOWN_TIME = 20

AUTO_MAINTENANCE_THRESHOLD = 0.85
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
                    "M_3": None
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
                    agent_alerts.append({
                        "machine_id": mid,
                        "level": "CRITICAL" if risk > 0.7 else "WARNING",
                        "message": f"Failure risk {round(risk*100)}%"
                    })

                
                
                # ==========================================
                # 🔧 MAINTENANCE (STRICT - ONLY CRITICAL)
                # ==========================================
                if m.get("health_status") == "Critical":

                    # extra safety: ensure truly degraded
                    if (
                        m.get("prediction", 0) > 0.85
                        and m.get("tool_wear", 0) > 0.8
                    ):

                        if mid not in MAINTENANCE_COOLDOWN:

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

            await ws.send_json({
                "machines": analyzed,
                "factory_analytics": analytics,
                "agent_alerts": agent_alerts,
                "agent_actions": agent_actions
            })

            await asyncio.sleep(1)

    except Exception as e:
        print("❌ WebSocket error:", e)

    finally:
        print("🔌 WebSocket closed")