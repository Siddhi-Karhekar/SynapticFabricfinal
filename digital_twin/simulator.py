# digital_twin/simulator.py
#
# Synaptic Fabric - Nexus Edition
# 4-node manufacturing chain with causal physics propagation:
#
#   M_1 Induction Motor  ->  M_2 Industrial Gearbox  ->
#   M_3 CNC Milling Tool ->  M_4 Robotic Sorting Arm
#
# Anomaly causality (with physics-based delay):
#   torque spike (motor) -> vibration (gearbox) ->
#   thermal runaway (mill) -> overstrain (arm)

import random
from collections import deque

# ==========================================
# CHAIN ORDER (upstream -> downstream)
# ==========================================
CHAIN = ["M_1", "M_2", "M_3", "M_4"]

# ==========================================
# MACHINE MEMORY (STATEFUL)
# ==========================================
MACHINE_MEMORY = {
    "M_1": {
        "tool_wear": 0.10,
        "vibration_index": 0.20,
        "temperature": 295,
        "torque": 40,
    },
    "M_2": {
        "tool_wear": 0.08,
        "vibration_index": 0.18,
        "temperature": 295,
        "torque": 42,
    },
    "M_3": {
        "tool_wear": 0.10,
        "vibration_index": 0.15,
        "temperature": 296,
        "torque": 44,
    },
    "M_4": {
        "tool_wear": 0.06,
        "vibration_index": 0.12,
        "temperature": 295,
        "torque": 46,
    },
}

# ==========================================
# CAUSAL PROPAGATION BUFFERS
# Each buffer is a small queue holding the upstream
# disturbance until enough physics-based "ticks" have
# elapsed. This is what produces realistic delay
# between the upstream cause and downstream effect.
# ==========================================
PROPAGATION_DELAY = {
    "M_1->M_2": 2,   # torque spike reaches gearbox after ~2 ticks
    "M_2->M_3": 3,   # vibration drives milling thermal runaway
    "M_3->M_4": 4,   # thermal stress shows up as arm overstrain
}

PROP_BUFFERS = {
    edge: deque([0.0] * delay, maxlen=delay)
    for edge, delay in PROPAGATION_DELAY.items()
}


# ==========================================
# HELPER
# ==========================================
def clamp(val, min_val, max_val):
    return max(min_val, min(val, max_val))


def _push_propagation(edge, value):
    PROP_BUFFERS[edge].append(value)
    return PROP_BUFFERS[edge][0]


# ==========================================
# DIGITAL TWIN ENGINE
# ==========================================
def run_digital_twin():

    # ------------------------------------------
    # 1. UPSTREAM SOURCE: Induction Motor (M_1)
    #    primary disturbance = torque spike
    # ------------------------------------------
    m1 = MACHINE_MEMORY["M_1"]
    m1["tool_wear"] += random.uniform(0.0003, 0.0007) * (1 + m1["tool_wear"] ** 2)
    m1["temperature"] += random.uniform(0.04, 0.10)

    # baseline torque ~ load + wear coupling
    m1["torque"] = 40 + m1["tool_wear"] * 25 + random.uniform(-0.5, 0.5)

    # rare torque spike (root cause event)
    torque_spike = 0.0
    if random.random() < 0.04:
        torque_spike = random.uniform(8, 18)
        m1["torque"] += torque_spike

    if m1["torque"] > 70:
        m1["temperature"] += 0.20  # I^2R heating from over-current

    # ------------------------------------------
    # 2. M_2 Industrial Gearbox
    #    receives torque disturbance -> vibration
    # ------------------------------------------
    delayed_torque = _push_propagation("M_1->M_2", torque_spike)
    m2 = MACHINE_MEMORY["M_2"]

    m2["tool_wear"] += random.uniform(0.0002, 0.0005) * (1 + m2["tool_wear"] ** 2)
    m2["torque"] = m1["torque"] * 0.92 + random.uniform(-0.4, 0.4)

    # vibration is the downstream effect of upstream torque
    m2["vibration_index"] += 0.0003 + 0.012 * delayed_torque
    m2["vibration_index"] += random.uniform(0.0001, 0.0004)
    m2["temperature"] += random.uniform(0.03, 0.09)

    if m2["vibration_index"] > 0.5:
        m2["temperature"] += 0.10

    # forward gearbox vibration to milling tool
    vib_spike = max(0.0, m2["vibration_index"] - 0.30)

    # ------------------------------------------
    # 3. M_3 CNC Milling Tool
    #    receives vibration -> thermal runaway
    # ------------------------------------------
    delayed_vib = _push_propagation("M_2->M_3", vib_spike)
    m3 = MACHINE_MEMORY["M_3"]

    m3["tool_wear"] += random.uniform(0.0004, 0.0009)
    m3["tool_wear"] += delayed_vib * 0.0025  # vibration accelerates wear
    m3["torque"] = 44 + m3["tool_wear"] * 22 + random.uniform(-0.5, 0.5)

    # thermal runaway: heat = friction(wear) + vibration coupling
    friction_heat = m3["tool_wear"] * 0.6
    vib_heat = delayed_vib * 1.8
    m3["temperature"] += 0.04 + friction_heat * 0.4 + vib_heat * 0.4

    m3["vibration_index"] = clamp(
        m3["vibration_index"] * 0.98 + delayed_vib * 0.6,
        0,
        1,
    )

    thermal_stress = max(0.0, m3["temperature"] - 305)

    # ------------------------------------------
    # 4. M_4 Robotic Sorting Arm
    #    receives thermal stress -> overstrain
    # ------------------------------------------
    delayed_heat = _push_propagation("M_3->M_4", thermal_stress)
    m4 = MACHINE_MEMORY["M_4"]

    m4["tool_wear"] += random.uniform(0.0002, 0.0005)
    m4["temperature"] += random.uniform(0.02, 0.07) + delayed_heat * 0.15

    # overstrain expressed as torque/vibration coupling
    m4["torque"] = 46 + m4["tool_wear"] * 28 + delayed_heat * 1.2
    m4["vibration_index"] += 0.0002 + delayed_heat * 0.0035
    m4["vibration_index"] += random.uniform(0.0001, 0.0003)

    # ------------------------------------------
    # 5. SHARED THERMAL DYNAMICS + LIMITS
    # ------------------------------------------
    machines = []
    for mid in CHAIN:
        s = MACHINE_MEMORY[mid]

        # natural cooling
        if s["temperature"] > 300:
            s["temperature"] -= random.uniform(0.04, 0.10)

        # mild self-recovery on vibration
        if random.random() < 0.03:
            s["vibration_index"] *= 0.99

        # damage-driven heat amplification
        if s["tool_wear"] > 0.6:
            s["temperature"] += 0.05
        if s["tool_wear"] > 0.85:
            s["temperature"] += 0.15

        # clamp
        s["tool_wear"] = clamp(s["tool_wear"], 0, 1)
        s["vibration_index"] = clamp(s["vibration_index"], 0, 1)
        s["temperature"] = clamp(s["temperature"], 290, 330)
        s["torque"] = clamp(s["torque"], 30, 95)

        machines.append({
            "machine_id": mid,
            "temperature": round(s["temperature"], 2),
            "torque": round(s["torque"], 2),
            "tool_wear": round(s["tool_wear"], 4),
            "vibration_index": round(s["vibration_index"], 4),
        })

    return machines
