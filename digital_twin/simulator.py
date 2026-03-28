# digital_twin/simulator.py

import random

# ==========================================
# MACHINE MEMORY (STATEFUL)
# ==========================================

MACHINE_MEMORY = {
    "M_1": {
        "tool_wear": 0.12,
        "vibration_index": 0.30,
        "temperature": 295,
        "torque": 40
    },
    "M_2": {
        "tool_wear": 0.08,
        "vibration_index": 0.18,
        "temperature": 295,
        "torque": 40
    },
    "M_3": {
        "tool_wear": 0.10,
        "vibration_index": 0.15,
        "temperature": 295,
        "torque": 42
    },
}

# ==========================================
# HELPER
# ==========================================

def clamp(val, min_val, max_val):
    return max(min_val, min(val, max_val))


# ==========================================
# DIGITAL TWIN ENGINE (REALISTIC - FIXED)
# ==========================================

def run_digital_twin():

    machines = []

    for machine_id, state in MACHINE_MEMORY.items():

        # ======================================
        # 🔵 BASE DEGRADATION (NON-LINEAR FIX)
        # ======================================
        base_wear = random.uniform(0.0003, 0.0008)

        # aging accelerates smoothly (no sudden jump)
        aging_factor = 1 + (state["tool_wear"] ** 2) * 2

        state["tool_wear"] += base_wear * aging_factor
        state["vibration_index"] += random.uniform(0.0002, 0.0006) * aging_factor

        # ======================================
        # 🔥 CONTROLLED AGING (PREVENT JUMPS)
        # ======================================
        if state["tool_wear"] > 0.6:
            state["tool_wear"] += 0.0005

        if state["tool_wear"] > 0.8:
            state["tool_wear"] += 0.001

        # ======================================
        # 🔵 CNC MILLING (M1)
        # ======================================
        if machine_id == "M_1":

            state["vibration_index"] += random.uniform(0.001, 0.004)

            # reduced aggressiveness (fix jump)
            state["tool_wear"] += state["vibration_index"] * 0.0015

            # occasional shock (kept realistic)
            if random.random() < 0.02:
                state["vibration_index"] += random.uniform(0.03, 0.07)

            state["temperature"] += random.uniform(0.05, 0.12)

        # ======================================
        # 🟡 CNC DRILLING (M2)
        # ======================================
        elif machine_id == "M_2":

            state["temperature"] += random.uniform(0.08, 0.2)

            if state["temperature"] > 300:
                state["tool_wear"] += 0.0015

            if state["temperature"] > 310:
                state["temperature"] -= random.uniform(0.4, 0.8)

            state["vibration_index"] += random.uniform(0.0002, 0.0005)

        # ======================================
        # 🟢 CNC LATHE (M3)
        # ======================================
        elif machine_id == "M_3":

            state["torque"] = 40 + state["tool_wear"] * 30

            state["tool_wear"] += random.uniform(0.0004, 0.001)

            if random.random() < 0.015:
                state["torque"] += random.uniform(5, 10)

            state["vibration_index"] *= 0.995

            state["temperature"] += random.uniform(0.04, 0.1)

        # ======================================
        # 🌡 TEMPERATURE ESCALATION WITH DAMAGE
        # ======================================
        if state["tool_wear"] > 0.5:
            state["temperature"] += 0.08

        if state["tool_wear"] > 0.7:
            state["temperature"] += 0.15

        if state["tool_wear"] > 0.85:
            state["temperature"] += 0.25

        # ======================================
        # 🌡 NATURAL COOLING (WEAK BUT STABLE)
        # ======================================
        if state["temperature"] > 300:
            state["temperature"] -= random.uniform(0.05, 0.12)

        # ======================================
        # 🔁 NATURAL RECOVERY (VERY MINOR)
        # ======================================
        if random.random() < 0.03:
            state["vibration_index"] *= 0.99

        # ======================================
        # LIMITS (IMPORTANT FOR STABILITY)
        # ======================================
        state["tool_wear"] = clamp(state["tool_wear"], 0, 1)
        state["vibration_index"] = clamp(state["vibration_index"], 0, 1)
        state["temperature"] = clamp(state["temperature"], 290, 330)
        state["torque"] = clamp(state["torque"], 35, 90)

        # ======================================
        # OUTPUT
        # ======================================
        machines.append({
            "machine_id": machine_id,
            "temperature": round(state["temperature"], 2),
            "torque": round(state["torque"], 2),
            "tool_wear": round(state["tool_wear"], 4),
            "vibration_index": round(state["vibration_index"], 4)
        })

    return machines