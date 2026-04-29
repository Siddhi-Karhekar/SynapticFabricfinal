# ==========================================
# CHATBOT API
#
# Two-tier design for speed:
#   FAST PATH (no LLM, ~10ms): metric lookups, machine status, comparisons
#   LLM PATH (phi3:mini):      "why", "what should I do", "explain", history
#
# The fast path answers ~70% of real-time queries instantly.
# The LLM path keeps the prompt small so first token arrives quickly.
# ==========================================

import re

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend_fastapi.database.database import get_db
from backend_fastapi.app.state import LIVE_MACHINES
from backend_fastapi.chatbot.history_tools import get_recent_events
from backend_fastapi.chatbot.llm_client import (
    generate_llm_stream,
    generate_llm_response,
)

router = APIRouter()


MACHINE_NAMES = {
    "M_1": "Induction Motor",
    "M_2": "Industrial Gearbox",
    "M_3": "CNC Milling Tool",
    "M_4": "Robotic Sorting Arm",
}
CHAIN = ["M_1", "M_2", "M_3", "M_4"]


SYSTEM_PROMPT = (
    "You are the AI assistant for a 4-stage factory line: "
    "M_1 Motor -> M_2 Gearbox -> M_3 CNC Mill -> M_4 Robot Arm. "
    "Failures propagate downstream (torque -> vibration -> heat -> overstrain). "
    "Answer in 1-2 short, plain-English sentences. "
    "Use only the data given. For 'why', name the cause. For advice, give one action."
)


# ==========================================
# FAST PATH — pattern lookups, no LLM
# ==========================================
METRIC_PATTERNS = [
    ("temperature", r"\b(temp|temperature|hot|heat|cooling)\b", "C", 1.0, 1, "C"),
    ("vibration_index", r"\b(vibration|vib|shaking|shake)\b", "", 1.0, 3, ""),
    ("torque", r"\b(torque)\b", "Nm", 1.0, 1, "Nm"),
    ("tool_wear", r"\b(wear|worn)\b", "%", 100.0, 0, "%"),
    ("prediction", r"\b(risk|failure|fail|chance)\b", "%", 100.0, 0, "%"),
]

STATUS_RE = re.compile(r"\b(status|health|condition|how is|how's)\b", re.I)
WORST_RE = re.compile(
    r"\b(worst|most stressed|most unstable|most critical|highest risk|in trouble)\b",
    re.I,
)
BEST_RE = re.compile(r"\b(best|healthiest|least risk|safest|fine)\b", re.I)
LIST_RE = re.compile(r"\b(list|all machines|every machine|overview|summary)\b", re.I)
PLANT_RE = re.compile(r"\b(plant|factory|overall|whole)\b", re.I)
ALERT_RE = re.compile(r"\b(alert|alarm|warning|critical)s?\b", re.I)


def _machine_id(q: str):
    m = re.search(r"\bm[_\s\-]?([1-4])\b", q.lower())
    return f"M_{m.group(1)}" if m else None


def _fmt_machine(mid: str, m: dict) -> str:
    return (
        f"{mid} ({MACHINE_NAMES[mid]}): {m.get('health_status', '?')}, "
        f"temp {m.get('temperature', 0):.1f}°C, "
        f"vib {m.get('vibration_index', 0):.3f}, "
        f"risk {m.get('prediction', 0) * 100:.0f}%"
    )


def fast_answer(q: str):
    """Return a string if the query can be answered without the LLM, else None."""
    if not LIVE_MACHINES:
        return None

    ql = q.lower().strip()
    mid = _machine_id(q)

    # "list/all/overview"
    if LIST_RE.search(ql):
        return "\n".join(
            _fmt_machine(m, LIVE_MACHINES[m]) for m in CHAIN if m in LIVE_MACHINES
        )

    # "which is worst / most stressed"
    if WORST_RE.search(ql):
        worst = max(LIVE_MACHINES.values(), key=lambda x: x.get("prediction", 0))
        return (
            f"{worst['machine_id']} ({MACHINE_NAMES[worst['machine_id']]}) is most stressed: "
            f"{worst.get('prediction', 0) * 100:.0f}% risk, "
            f"{worst.get('health_status', '?')}."
        )

    if BEST_RE.search(ql):
        best = min(LIVE_MACHINES.values(), key=lambda x: x.get("prediction", 0))
        return (
            f"{best['machine_id']} ({MACHINE_NAMES[best['machine_id']]}) is healthiest: "
            f"{best.get('prediction', 0) * 100:.0f}% risk."
        )

    # "plant health"
    if PLANT_RE.search(ql) and not mid:
        risks = [m.get("prediction", 0) for m in LIVE_MACHINES.values()]
        avg = sum(risks) / len(risks) if risks else 0
        attention = [
            m["machine_id"]
            for m in LIVE_MACHINES.values()
            if m.get("health_status") and m["health_status"] != "Healthy"
        ]
        att = f"Attention: {', '.join(attention)}." if attention else "All healthy."
        return f"Plant health {round((1 - avg) * 100, 1)}%. {att}"

    # "alerts / warnings"
    if ALERT_RE.search(ql) and not _is_reasoning(ql):
        active = []
        for m in LIVE_MACHINES.values():
            if m.get("health_status") and m["health_status"] != "Healthy":
                active.append(
                    f"{m['machine_id']}: {m.get('health_status')} "
                    f"({m.get('prediction', 0) * 100:.0f}% risk)"
                )
        return "\n".join(active) if active else "No active alerts. All machines healthy."

    # Specific machine queries
    if mid and mid in LIVE_MACHINES:
        m = LIVE_MACHINES[mid]

        # "status / health of M_x"
        if STATUS_RE.search(ql):
            return _fmt_machine(mid, m)

        # specific metric
        for key, pat, _, mult, prec, unit in METRIC_PATTERNS:
            if re.search(pat, ql, re.I):
                v = m.get(key)
                if v is None:
                    continue
                # "why" or "explain" with metric → let LLM handle reasoning
                if _is_reasoning(ql):
                    return None
                shown = v * mult
                u = f"°{unit}" if unit == "C" else (f" {unit}" if unit and unit != "%" else unit)
                return f"{mid} {key.replace('_', ' ')}: {shown:.{prec}f}{u}."

    return None


# ==========================================
# LLM PATH — only when reasoning is required
# ==========================================
REASONING_RE = re.compile(
    r"\b(why|how|explain|cause|reason|because|suggest|recommend|advise|"
    r"fix|solve|should i|what.*do|what.*next|analyz|insight|trend)\b",
    re.I,
)
HISTORY_RE = re.compile(
    r"\b(history|earlier|ago|happened|past|minute|hour|before|previous|since|trend)\b",
    re.I,
)


def _is_reasoning(q: str) -> bool:
    return bool(REASONING_RE.search(q))


def _live_block(focus_id: str = None) -> str:
    if not LIVE_MACHINES:
        return "Live readings: not yet available."

    ids = [focus_id] if focus_id and focus_id in LIVE_MACHINES else CHAIN
    lines = ["LIVE:"]
    for mid in ids:
        m = LIVE_MACHINES.get(mid)
        if not m:
            continue
        lines.append(
            f"{mid} {MACHINE_NAMES[mid]}: "
            f"T={m.get('temperature', 0):.1f}C, "
            f"V={m.get('vibration_index', 0):.3f}, "
            f"Tq={m.get('torque', 0):.1f}, "
            f"wear={m.get('tool_wear', 0) * 100:.0f}%, "
            f"risk={m.get('prediction', 0) * 100:.0f}%, "
            f"{m.get('health_status', '?')}"
        )
        rc = m.get("root_cause") or []
        issues = [c.get("issue") for c in rc if isinstance(c, dict) and c.get("issue")]
        if issues:
            lines.append(f"  cause: {issues[0]}")
    return "\n".join(lines)


def _history_block(db: Session, focus_id: str = None, minutes: int = 10) -> str:
    try:
        logs = get_recent_events(db, minutes=minutes)
        if not logs:
            return ""

        per = {}
        for l in logs:
            if focus_id and l.machine_id != focus_id:
                continue
            mid = l.machine_id
            if mid not in per:
                per[mid] = {"max_t": 0, "max_v": 0, "max_r": 0, "crit": 0}
            p = per[mid]
            p["max_t"] = max(p["max_t"], l.temperature or 0)
            p["max_v"] = max(p["max_v"], l.vibration_index or 0)
            p["max_r"] = max(p["max_r"], l.failure_probability or 0)
            if l.health_status == "Critical":
                p["crit"] += 1

        if not per:
            return ""
        lines = [f"LAST {minutes}min:"]
        for mid in CHAIN:
            if mid not in per:
                continue
            p = per[mid]
            lines.append(
                f"{mid}: peak T={p['max_t']:.1f}, V={p['max_v']:.3f}, "
                f"risk={p['max_r'] * 100:.0f}%, critical_ticks={p['crit']}"
            )
        return "\n".join(lines)
    except Exception as e:
        print("HIST ERR:", e)
        return ""


def _build_prompt(question: str, db: Session) -> str:
    focus = _machine_id(question)
    parts = [_live_block(focus_id=focus)]

    if HISTORY_RE.search(question):
        h = _history_block(db, focus_id=focus, minutes=10)
        if h:
            parts.append(h)

    parts.append(f"Q: {question}\nA (1-2 sentences):")
    return "\n\n".join(parts)


# ==========================================
# ENDPOINTS
# ==========================================
@router.post("/chat/stream")
def chat_stream(payload: dict, db: Session = Depends(get_db)):
    question = (payload.get("message") or "").strip()
    if not question:
        return StreamingResponse(iter(["Please ask a question."]), media_type="text/plain")

    # 1. fast deterministic path
    fast = fast_answer(question)
    if fast is not None:
        return StreamingResponse(iter([fast]), media_type="text/plain")

    # 2. LLM reasoning path (slim prompt)
    prompt = _build_prompt(question, db)

    def gen():
        try:
            for token in generate_llm_stream(
                prompt, system_prompt=SYSTEM_PROMPT, num_predict=80
            ):
                yield token
        except Exception as e:
            print("STREAM ERR:", e)
            yield "Sorry, I hit an error. Try again."

    return StreamingResponse(gen(), media_type="text/plain")


@router.post("/chat")
def chat(payload: dict, db: Session = Depends(get_db)):
    """Non-streaming fallback."""
    question = (payload.get("message") or "").strip()
    if not question:
        return {"response": "Please ask a question."}

    fast = fast_answer(question)
    if fast is not None:
        return {"response": fast}

    try:
        prompt = _build_prompt(question, db)
        response = generate_llm_response(
            prompt, system_prompt=SYSTEM_PROMPT, num_predict=80
        )
        return {"response": response}
    except Exception as e:
        print("CHAT ERR:", e)
        return {"response": "Sorry, I hit an error. Try again."}
