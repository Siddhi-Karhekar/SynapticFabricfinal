# Root-cause analysis aligned to the 4-node chain:
#   M_1 Induction Motor   -> M_2 Industrial Gearbox
#   M_3 CNC Milling Tool  -> M_4 Robotic Sorting Arm

def analyze_root_cause(machine):

    mid = machine.get("machine_id", "Unknown")
    temp = machine.get("temperature", 0)
    vib = machine.get("vibration_index", 0)
    wear = machine.get("tool_wear", 0)
    torque = machine.get("torque", 0)

    causes = []

    # ------------------------------------------
    # GENERIC WEAR SIGNATURE
    # ------------------------------------------
    if wear > 0.85:
        causes.append({
            "issue": "Tool/component failure imminent",
            "confidence": wear,
            "reason": f"Wear at {round(wear*100,1)}%"
        })
    elif wear > 0.6:
        causes.append({
            "issue": "Component degradation",
            "confidence": wear,
            "reason": "Wear trending upward"
        })

    # ------------------------------------------
    # M_1 - Induction Motor: torque spikes / overcurrent
    # ------------------------------------------
    if mid == "M_1":
        if torque > 75:
            causes.append({
                "issue": "Stator overcurrent / torque spike",
                "confidence": 0.9,
                "reason": f"Torque {round(torque,1)} Nm exceeds nameplate"
            })
        elif torque > 60:
            causes.append({
                "issue": "Mechanical load surge",
                "confidence": 0.6,
                "reason": "Torque rising abnormally"
            })
        if temp > 308:
            causes.append({
                "issue": "Winding overheating",
                "confidence": 0.85,
                "reason": f"Stator temp {round(temp,1)}K"
            })

    # ------------------------------------------
    # M_2 - Industrial Gearbox: vibration / bearing
    # ------------------------------------------
    elif mid == "M_2":
        if vib > 0.8:
            causes.append({
                "issue": "Gearbox bearing failure",
                "confidence": vib,
                "reason": "Severe vibration on input shaft"
            })
        elif vib > 0.55:
            causes.append({
                "issue": "Gear mesh imbalance",
                "confidence": vib,
                "reason": "Moderate vibration coupling from motor"
            })
        if torque > 70:
            causes.append({
                "issue": "Transmitted torque overload",
                "confidence": 0.8,
                "reason": "Upstream motor spike propagated"
            })

    # ------------------------------------------
    # M_3 - CNC Milling Tool: thermal runaway
    # ------------------------------------------
    elif mid == "M_3":
        if temp > 312:
            causes.append({
                "issue": "Thermal runaway (cooling failure)",
                "confidence": 0.95,
                "reason": f"Tool temp {round(temp,1)}K, vibration coupling"
            })
        elif temp > 305:
            causes.append({
                "issue": "Heat buildup at cutter",
                "confidence": 0.7,
                "reason": "Friction + upstream vibration"
            })
        if vib > 0.7:
            causes.append({
                "issue": "Spindle imbalance from upstream",
                "confidence": vib,
                "reason": "Vibration arriving from gearbox"
            })

    # ------------------------------------------
    # M_4 - Robotic Sorting Arm: overstrain
    # ------------------------------------------
    elif mid == "M_4":
        if torque > 70:
            causes.append({
                "issue": "Joint actuator overstrain",
                "confidence": 0.9,
                "reason": f"Torque {round(torque,1)} Nm at end effector"
            })
        elif torque > 58:
            causes.append({
                "issue": "Payload handling stress",
                "confidence": 0.6,
                "reason": "Torque trending high"
            })
        if temp > 308:
            causes.append({
                "issue": "Servo thermal stress",
                "confidence": 0.75,
                "reason": "Heat propagated from milling stage"
            })

    if not causes:
        causes.append({
            "issue": "Normal operation",
            "confidence": 0.2,
            "reason": "Stable parameters"
        })

    return sorted(causes, key=lambda x: x["confidence"], reverse=True)
