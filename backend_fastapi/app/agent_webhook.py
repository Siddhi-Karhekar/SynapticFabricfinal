# ==========================================
# AGENT WEBHOOK
# n8n posts corrective-action decisions here.
# This is the "closed-loop" part of the pipeline.
# ==========================================

import time
import logging
from typing import Optional, Any

from fastapi import APIRouter
from pydantic import BaseModel

from digital_twin.simulator import MACHINE_MEMORY
from backend_fastapi.app.state import LIVE_MACHINES

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
    if action == "AUTO_MAINTENANCE" and mid in MACHINE_MEMORY:
        s = MACHINE_MEMORY[mid]
        s["tool_wear"] *= 0.15
        s["vibration_index"] *= 0.25
        s["temperature"] = max(s["temperature"] - 8, 295)
        s["torque"] *= 0.92
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

    return {"status": "ok", "applied": applied, "machine_id": mid}


@router.get("/agent/actions")
def list_actions(limit: int = 20):
    return RECENT_AGENT_ACTIONS[-limit:]


@router.get("/agent/health")
def health():
    return {
        "status": "ok",
        "live_machines": list(LIVE_MACHINES.keys()),
    }
