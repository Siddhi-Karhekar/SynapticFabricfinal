# ==========================================
# AGENT WEBHOOK
# n8n posts corrective-action decisions here.
# This is the "closed-loop" part of the pipeline.
# ==========================================

import csv
import io
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Optional, Any

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from digital_twin.simulator import MACHINE_MEMORY, reset_inbound_buffers
from backend_fastapi.app.state import LIVE_MACHINES, WHATIF_SNAPSHOTS
from backend_fastapi.database.database import SessionLocal
from backend_fastapi.database.models import MaintenanceLog
from backend_fastapi.database.maintenance_log import record_maintenance

logger = logging.getLogger("agent_webhook")
logger.setLevel(logging.INFO)

router = APIRouter()

# Recent agent actions surfaced via the WS payload as well.
RECENT_AGENT_ACTIONS: list[dict] = []


class AgentAction(BaseModel):
    machine_id: str
    action: str
    reason: Optional[str] = None
    justification: Optional[Any] = None
    source: Optional[str] = "n8n"


@router.post("/agent/action")
def agent_action(payload: AgentAction):

    mid = payload.machine_id
    action = payload.action.upper()

    logger.info(f"⚡ AGENT ACTION recv: {mid} -> {action} ({payload.source})")

    applied = False

    # ---------------------------------------------
    # AUTO_MAINTENANCE -> reset the digital twin
    # like the local maintenance button would.
    # ---------------------------------------------
    is_whatif_revert = False
    coreverted = []
    if action == "AUTO_MAINTENANCE" and mid in MACHINE_MEMORY:
        s = MACHINE_MEMORY[mid]
        if WHATIF_SNAPSHOTS:
            # Drain the whole what-if scenario.
            for other_id in list(WHATIF_SNAPSHOTS.keys()):
                snap = WHATIF_SNAPSHOTS.pop(other_id)
                if other_id in MACHINE_MEMORY:
                    MACHINE_MEMORY[other_id].update(snap)
                    reset_inbound_buffers(other_id)
                if other_id != mid:
                    coreverted.append(other_id)
            is_whatif_revert = True
        else:
            s["tool_wear"] *= 0.15
            s["vibration_index"] *= 0.25
            s["temperature"] = max(s["temperature"] - 8, 295)
            s["torque"] *= 0.92
            reset_inbound_buffers(mid)
        applied = True

    # ---------------------------------------------
    # NOTIFY_OPERATOR -> just log
    # ---------------------------------------------
    elif action == "NOTIFY_OPERATOR":
        applied = True

    record = {
        "machine_id": mid,
        "action": action,
        "status": "APPLIED" if applied else "IGNORED",
        "reason": payload.reason,
        "justification": payload.justification,
        "source": payload.source,
        "timestamp": time.time(),
    }
    RECENT_AGENT_ACTIONS.append(record)

    # cap memory
    if len(RECENT_AGENT_ACTIONS) > 50:
        del RECENT_AGENT_ACTIONS[0:25]

    live = LIVE_MACHINES.get(mid, {})
    record_maintenance(
        machine_id=mid,
        action="WHAT_IF_REVERT" if is_whatif_revert else action,
        status="APPLIED" if applied else "IGNORED",
        source=payload.source or "n8n",
        reason=(
            "Reverted what-if scenario via n8n agent action"
            if is_whatif_revert
            else payload.reason
        ),
        health_status=live.get("health_status"),
        risk=live.get("prediction"),
        is_whatif=is_whatif_revert,
    )
    for other_id in coreverted:
        ol = LIVE_MACHINES.get(other_id, {})
        record_maintenance(
            machine_id=other_id,
            action="WHAT_IF_REVERT",
            status="APPLIED",
            source=payload.source or "n8n",
            reason="Co-reverted as part of what-if scenario via n8n",
            health_status=ol.get("health_status"),
            risk=ol.get("prediction"),
            is_whatif=True,
        )

    return {
        "status": "ok",
        "applied": applied,
        "machine_id": mid,
        "reverted_whatif": is_whatif_revert,
        "co_reverted": coreverted,
    }


@router.get("/agent/actions")
def list_actions(limit: int = 20):
    return RECENT_AGENT_ACTIONS[-limit:]


@router.get("/maintenance/logs")
def maintenance_logs(
    minutes: Optional[int] = Query(None, ge=1, le=10080),
    machine_id: Optional[str] = None,
    limit: int = Query(500, ge=1, le=10000),
):
    db = SessionLocal()
    try:
        q = db.query(MaintenanceLog)
        if minutes is not None:
            cutoff = datetime.utcnow() - timedelta(minutes=minutes)
            q = q.filter(MaintenanceLog.timestamp >= cutoff)
        if machine_id:
            q = q.filter(MaintenanceLog.machine_id == machine_id)
        rows = q.order_by(MaintenanceLog.timestamp.desc()).limit(limit).all()
        return [
            {
                "id": r.id,
                "timestamp": r.timestamp.isoformat() + "Z",
                "machine_id": r.machine_id,
                "action": r.action,
                "status": r.status,
                "source": r.source,
                "reason": r.reason,
                "health_status": r.health_status,
                "risk": r.risk,
                "is_whatif": bool(r.is_whatif),
            }
            for r in rows
        ]
    finally:
        db.close()


@router.get("/maintenance/logs/download")
def download_maintenance_logs(
    format: str = Query("csv", pattern="^(csv|json)$"),
    minutes: Optional[int] = Query(None, ge=1, le=10080),
    machine_id: Optional[str] = None,
):
    db = SessionLocal()
    try:
        q = db.query(MaintenanceLog)
        if minutes is not None:
            cutoff = datetime.utcnow() - timedelta(minutes=minutes)
            q = q.filter(MaintenanceLog.timestamp >= cutoff)
        if machine_id:
            q = q.filter(MaintenanceLog.machine_id == machine_id)
        rows = q.order_by(MaintenanceLog.timestamp.asc()).all()

        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        if format == "json":
            payload = [
                {
                    "id": r.id,
                    "timestamp": r.timestamp.isoformat() + "Z",
                    "machine_id": r.machine_id,
                    "action": r.action,
                    "status": r.status,
                    "source": r.source,
                    "reason": r.reason,
                    "health_status": r.health_status,
                    "risk": r.risk,
                    "is_whatif": bool(r.is_whatif),
                }
                for r in rows
            ]
            return JSONResponse(
                content=payload,
                headers={
                    "Content-Disposition": f'attachment; filename="maintenance_logs_{stamp}.json"'
                },
            )

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "id",
                "timestamp_utc",
                "machine_id",
                "action",
                "status",
                "source",
                "is_whatif",
                "health_status",
                "risk",
                "reason",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    r.id,
                    r.timestamp.isoformat() + "Z",
                    r.machine_id,
                    r.action,
                    r.status,
                    r.source,
                    "true" if bool(r.is_whatif) else "false",
                    r.health_status or "",
                    "" if r.risk is None else f"{r.risk:.4f}",
                    (r.reason or "").replace("\n", " ").replace("\r", " "),
                ]
            )
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="maintenance_logs_{stamp}.csv"'
            },
        )
    finally:
        db.close()


@router.get("/agent/health")
def health():
    return {
        "status": "ok",
        "live_machines": list(LIVE_MACHINES.keys()),
    }
