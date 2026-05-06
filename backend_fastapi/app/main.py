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

from digital_twin.simulator import (
    run_digital_twin,
    MACHINE_MEMORY,
    reset_inbound_buffers,
)
from backend_fastapi.ai_engine.machine_analyzer import machine_analyzer
from backend_fastapi.app.chatbot_api import router as chatbot_router
from backend_fastapi.app.agent_webhook import router as agent_router, RECENT_AGENT_ACTIONS
from backend_fastapi.app.n8n_client import send_alert as n8n_send_alert
from backend_fastapi.database.database import SessionLocal, get_db, engine, Base
from backend_fastapi.database.models import MachineLog
from backend_fastapi.database.maintenance_log import record_maintenance
from backend_fastapi.chatbot.rag_service import build_context_from_db
from backend_fastapi.chatbot.llm_client import warmup as warmup_llm
from backend_fastapi.app.state import LIVE_MACHINES, WHATIF_SNAPSHOTS
from pydantic import BaseModel
from typing import Optional


# =====================================================
# CHAIN PROPAGATION FOR WHAT-IF SPIKES
# =====================================================
# Manufacturing chain order. A spike injected anywhere also drags the
# rest of the plant (downstream gets the brunt, upstream sees a small
# reflected effect for attribution). All affected machines are
# snapshotted so a single maintenance call can restore the whole plant.
CHAIN = ["M_1", "M_2", "M_3", "M_4"]
CHAIN_INDEX = {mid: i for i, mid in enumerate(CHAIN)}

# attenuation factor by signed chain distance from origin.
# +N = downstream by N steps, -N = upstream by N steps.
_CHAIN_ATTENUATION = {
    -3: 0.05,
    -2: 0.10,
    -1: 0.20,
     0: 1.00,
     1: 0.60,
     2: 0.40,
     3: 0.25,
}


def _chain_targets(origin_id: str):
    """Yield (target_machine_id, attenuation) pairs for every chain
    machine, including the origin (1.0)."""
    if origin_id not in CHAIN_INDEX:
        return []
    o = CHAIN_INDEX[origin_id]
    out = []
    for i, mid in enumerate(CHAIN):
        att = _CHAIN_ATTENUATION.get(i - o, 0.0)
        if att > 0:
            out.append((mid, att))
    return out


def _clamp_field(field: str, value: float) -> float:
    if field in ("tool_wear", "vibration_index"):
        return float(max(0.0, min(value, 1.0)))
    if field == "temperature":
        return float(max(290.0, min(value, 330.0)))
    if field == "torque":
        return float(max(30.0, min(value, 95.0)))
    return float(value)


def _drain_whatif_scenario(reason: str, source: str):
    """Restore every machine that has a what-if snapshot. Returns the
    list of (machine_id, log_record_dict) pairs for the caller to log.
    """
    restored = []
    for mid in list(WHATIF_SNAPSHOTS.keys()):
        snap = WHATIF_SNAPSHOTS.pop(mid)
        if mid in MACHINE_MEMORY:
            MACHINE_MEMORY[mid].update(snap)
            reset_inbound_buffers(mid)
        live = LIVE_MACHINES.get(mid, {})
        restored.append({
            "machine_id": mid,
            "action": "WHAT_IF_REVERT",
            "status": "APPLIED",
            "source": source,
            "reason": reason,
            "health_status": live.get("health_status"),
            "risk": live.get("prediction"),
            "is_whatif": True,
        })
    return restored


def _apply_maintenance_or_revert(machine_id: str, source: str, reason_default: str):
    """Apply maintenance to a machine. If ANY what-if snapshots are
    active anywhere in the plant, drain the full scenario instead of
    doing the standard reset on this machine alone.

    Returns (action, reason, is_whatif, extra_revert_records).
    extra_revert_records is a list of additional log rows (one per
    non-origin machine restored as part of the same scenario) that the
    caller should record after the primary log entry.
    """
    if WHATIF_SNAPSHOTS:
        # Drain the whole scenario; the maintained machine takes the
        # primary log row, the rest are returned for the caller to log.
        records = _drain_whatif_scenario(
            reason=f"Reverted what-if scenario via {source}",
            source=source,
        )
        primary = next(
            (r for r in records if r["machine_id"] == machine_id),
            None,
        )
        extras = [r for r in records if r["machine_id"] != machine_id]
        if primary is None:
            # The maintained machine wasn't part of the scenario but
            # we still drained it — record this maintenance as a
            # normal reset for the maintained machine.
            s = MACHINE_MEMORY[machine_id]
            s["tool_wear"] *= 0.15
            s["vibration_index"] *= 0.25
            s["temperature"] = max(s["temperature"] - 8, 295)
            s["torque"] *= 0.92
            reset_inbound_buffers(machine_id)
            return (
                "MANUAL_MAINTENANCE" if source == "dashboard" else "AUTO_MAINTENANCE",
                reason_default,
                False,
                extras,
            )
        return ("WHAT_IF_REVERT",
                primary["reason"],
                True,
                extras)

    # No active what-if; standard reset path.
    s = MACHINE_MEMORY[machine_id]
    s["tool_wear"] *= 0.15
    s["vibration_index"] *= 0.25
    s["temperature"] = max(s["temperature"] - 8, 295)
    s["torque"] *= 0.92
    reset_inbound_buffers(machine_id)
    return ("MANUAL_MAINTENANCE" if source == "dashboard" else "AUTO_MAINTENANCE",
            reason_default,
            False,
            [])


app = FastAPI()


@app.on_event("startup")
def _create_tables():
    Base.metadata.create_all(bind=engine)
    # Lightweight migration: SQLite can't add columns via create_all,
    # so add is_whatif if an older maintenance_logs table is missing it.
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            cols = conn.execute(text("PRAGMA table_info(maintenance_logs)")).fetchall()
            existing = {c[1] for c in cols}
            if cols and "is_whatif" not in existing:
                conn.execute(text(
                    "ALTER TABLE maintenance_logs "
                    "ADD COLUMN is_whatif BOOLEAN DEFAULT 0 NOT NULL"
                ))
                conn.commit()
    except Exception as e:
        print("MIGRATION (is_whatif) skipped:", e)


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

    action, reason, is_whatif, extras = _apply_maintenance_or_revert(
        machine_id,
        source="dashboard",
        reason_default="Operator pressed Maintain on dashboard card",
    )
    MAINTENANCE_COOLDOWN[machine_id] = time.time()

    live = LIVE_MACHINES.get(machine_id, {})
    record_maintenance(
        machine_id=machine_id,
        action=action,
        status="APPLIED",
        source="dashboard",
        reason=reason,
        health_status=live.get("health_status"),
        risk=live.get("prediction"),
        is_whatif=is_whatif,
    )
    # Co-revert log rows for the rest of the scenario.
    for extra in extras:
        record_maintenance(**extra)

    # Emit STARTING + SUCCESS into RECENT_AGENT_ACTIONS so the dashboard
    # popup queue (driven by the WS agent_actions stream) shows the same
    # two-stage popup it shows for the auto-maintenance dwell rule.
    now = time.time()
    RECENT_AGENT_ACTIONS.append({
        "machine_id": machine_id,
        "action": action,
        "status": "STARTING",
        "timestamp": now,
        "source": "dashboard",
    })
    RECENT_AGENT_ACTIONS.append({
        "machine_id": machine_id,
        "action": action,
        "status": "SUCCESS",
        "timestamp": now + 0.001,
        "source": "dashboard",
    })
    for extra in extras:
        RECENT_AGENT_ACTIONS.append({
            "machine_id": extra["machine_id"],
            "action": extra["action"],
            "status": "SUCCESS",
            "timestamp": now + 0.002,
            "source": "dashboard",
        })
    if len(RECENT_AGENT_ACTIONS) > 50:
        del RECENT_AGENT_ACTIONS[0:25]

    return {
        "status": "success",
        "machine_id": machine_id,
        "reverted_whatif": is_whatif,
        "co_reverted": [e["machine_id"] for e in extras],
    }


# =====================================================
# WHAT-IF SPIKE INJECTION
# =====================================================
class SpikeRequest(BaseModel):
    temperature: Optional[float] = None
    torque: Optional[float] = None
    tool_wear: Optional[float] = None
    vibration_index: Optional[float] = None
    note: Optional[str] = None


@app.post("/spike/{machine_id}")
def inject_spike(machine_id: str, req: SpikeRequest):
    """Inject a hypothetical state on a machine and propagate scaled
    versions of the same deltas to the rest of the chain.

    Why propagate? A real failure in one machine doesn't sit in
    isolation — vibration in M_2 drags M_3 thermally, thermal stress in
    M_3 drags M_4 mechanically, etc. To let operators visualize "what
    happens to the whole plant if this machine fails", the spike is
    delta-applied to every machine with a chain-distance attenuation:

        downstream  +1: 60%   +2: 40%   +3: 25%
        upstream    -1: 20%   -2: 10%   -3: 5%

    Every affected machine is snapshotted before the override so that a
    single maintenance call (on any machine) reverts the entire plant.
    """
    if machine_id not in MACHINE_MEMORY:
        return {"status": "error", "message": "unknown machine"}

    origin = MACHINE_MEMORY[machine_id]

    # Compute deltas from the origin's CURRENT (pre-spike) state.
    deltas = {}
    if req.temperature is not None:
        deltas["temperature"] = float(req.temperature) - float(origin["temperature"])
    if req.torque is not None:
        deltas["torque"] = float(req.torque) - float(origin["torque"])
    if req.tool_wear is not None:
        deltas["tool_wear"] = float(req.tool_wear) - float(origin["tool_wear"])
    if req.vibration_index is not None:
        deltas["vibration_index"] = float(req.vibration_index) - float(origin["vibration_index"])

    if not deltas:
        return {"status": "error", "message": "no override fields supplied"}

    # Snapshot + apply deltas across the chain.
    affected = []
    for mid, att in _chain_targets(machine_id):
        s = MACHINE_MEMORY[mid]
        if mid not in WHATIF_SNAPSHOTS:
            WHATIF_SNAPSHOTS[mid] = dict(s)
        applied_here = {}
        for field, d in deltas.items():
            new_val = _clamp_field(field, float(s[field]) + d * att)
            s[field] = new_val
            applied_here[field] = new_val
        affected.append({
            "machine_id": mid,
            "attenuation": round(att, 2),
            "is_origin": (mid == machine_id),
            "applied": applied_here,
        })

    # One log row per affected machine. Origin uses the user's note,
    # others get a systematic "chain effect from <origin>" reason.
    note_suffix = f" | note: {req.note}" if req.note else ""
    for entry in affected:
        mid = entry["machine_id"]
        att = entry["attenuation"]
        live = LIVE_MACHINES.get(mid, {})
        if entry["is_origin"]:
            parts = [f"{k}={v:.3f}" for k, v in entry["applied"].items()]
            reason = f"WHAT-IF spike (origin): {', '.join(parts)}{note_suffix}"
        else:
            parts = [f"{k}={v:.3f}" for k, v in entry["applied"].items()]
            reason = (
                f"WHAT-IF chain effect from {machine_id} "
                f"(att={att}): {', '.join(parts)}"
            )
        record_maintenance(
            machine_id=mid,
            action="WHAT_IF_SPIKE",
            status="APPLIED",
            source="dashboard_whatif",
            reason=reason,
            health_status=live.get("health_status"),
            risk=live.get("prediction"),
            is_whatif=True,
        )

    return {
        "status": "success",
        "origin": machine_id,
        "affected": affected,
        "hint": (
            "Performing maintenance on ANY machine in this scenario "
            "will revert the whole plant to its pre-spike state."
        ),
    }


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

                    is_whatif_revert = bool(WHATIF_SNAPSHOTS)
                    base_action = "WHAT_IF_REVERT" if is_whatif_revert else "AUTO_MAINTENANCE"

                    agent_actions.append({
                        "machine_id": mid,
                        "action": base_action,
                        "status": "STARTING",
                        "timestamp": time.time()
                    })
                    record_maintenance(
                        machine_id=mid,
                        action=base_action,
                        status="STARTING",
                        source="dwell_rule",
                        reason=(
                            "Reverting what-if scenario (dwell rule fired)"
                            if is_whatif_revert
                            else f"Critical dwell >= {CRITICAL_DWELL_SECONDS}s"
                        ),
                        health_status=m.get("health_status"),
                        risk=risk,
                        is_whatif=is_whatif_revert,
                    )

                    await asyncio.sleep(1.5)

                    extra_records = []
                    if is_whatif_revert:
                        records = _drain_whatif_scenario(
                            reason="Reverted what-if scenario (dwell rule)",
                            source="dwell_rule",
                        )
                        # The maintained machine takes the SUCCESS row
                        # below; the rest go in extras.
                        extra_records = [
                            r for r in records if r["machine_id"] != mid
                        ]
                    else:
                        # 🔥 STRONG RESET (ENSURE REAL RECOVERY)
                        MACHINE_MEMORY[mid]["tool_wear"] *= 0.15
                        MACHINE_MEMORY[mid]["vibration_index"] *= 0.25
                        MACHINE_MEMORY[mid]["temperature"] -= 10
                        MACHINE_MEMORY[mid]["torque"] *= 0.9

                    reset_inbound_buffers(mid)
                    MAINTENANCE_COOLDOWN[mid] = time.time()
                    MACHINE_CRITICAL_SINCE.pop(mid, None)

                    agent_actions.append({
                        "machine_id": mid,
                        "action": base_action,
                        "status": "SUCCESS",
                        "timestamp": time.time()
                    })
                    record_maintenance(
                        machine_id=mid,
                        action=base_action,
                        status="SUCCESS",
                        source="dwell_rule",
                        reason=(
                            "Reverted what-if scenario (snapshot restored)"
                            if is_whatif_revert
                            else f"Reset applied after {CRITICAL_DWELL_SECONDS}s in Critical"
                        ),
                        health_status=m.get("health_status"),
                        risk=risk,
                        is_whatif=is_whatif_revert,
                    )
                    for extra in extra_records:
                        record_maintenance(**extra)

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