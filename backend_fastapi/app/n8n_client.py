# ==========================================
# n8n CLIENT
# Pushes alerts to the n8n agent pipeline.
# Fails silently when n8n isn't running so the
# rest of the system stays operational locally.
# ==========================================

import os
import json
import logging
import asyncio

import httpx

logger = logging.getLogger("n8n_client")
logger.setLevel(logging.INFO)

# Webhook URL on the n8n container.
# Override with N8N_WEBHOOK_URL env var if needed.
N8N_WEBHOOK_URL = os.environ.get(
    "N8N_WEBHOOK_URL",
    "http://localhost:5678/webhook/synfab-alert",
)

# Per-machine throttle: don't spam n8n for the same
# machine more than once every N seconds.
_LAST_SENT = {}
_THROTTLE_SECONDS = 8.0


async def _post(payload: dict, timeout: float = 4.0) -> bool:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(N8N_WEBHOOK_URL, json=payload)
            if resp.status_code >= 400:
                logger.warning(
                    "n8n webhook returned %s: %s",
                    resp.status_code,
                    resp.text[:200],
                )
                return False
            return True
    except Exception as e:
        # n8n not up yet, network problem, workflow not active, etc.
        logger.debug(f"n8n post skipped: {e}")
        return False


def _should_send(machine_id: str, now: float) -> bool:
    last = _LAST_SENT.get(machine_id, 0.0)
    if now - last < _THROTTLE_SECONDS:
        return False
    _LAST_SENT[machine_id] = now
    return True


async def send_alert(machine: dict, severity: str, risk: float):
    """
    Fire-and-forget alert to n8n. Severity is 'CRITICAL' or
    'WARNING'. Returns True on accept, False if skipped/failed.
    """
    import time
    now = time.time()
    mid = machine.get("machine_id", "UNKNOWN")

    if not _should_send(mid, now):
        return False

    payload = {
        "machine_id": mid,
        "severity": severity,
        "risk": float(risk),
        "temperature": machine.get("temperature"),
        "torque": machine.get("torque"),
        "tool_wear": machine.get("tool_wear"),
        "vibration_index": machine.get("vibration_index"),
        "pinn_temperature": machine.get("pinn_temperature"),
        "pinn_risk": machine.get("pinn_risk"),
        "gnn_risk": machine.get("gnn_risk"),
        "root_cause": machine.get("root_cause", []),
    }

    return await _post(payload)


def fire_and_forget(coro):
    """Schedule a coroutine without awaiting it (no blocking)."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
    except RuntimeError:
        asyncio.run(coro)
