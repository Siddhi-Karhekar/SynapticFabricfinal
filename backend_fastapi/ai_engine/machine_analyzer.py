import random
import logging

from backend_fastapi.ai_engine.root_cause import analyze_root_cause

# ✅ ML MODELS
from ml_models.failure_model import predict_failure
from ml_models.explainer import explain_prediction
from ml_models.anomaly_model import detect_anomaly

# ✅ TRANSFORMER
from ml_models.transformer_inference import predict_future

# ✅ GNN
from ml_models.gnn_inference import run_gnn


# ==========================================
# LOGGER
# ==========================================
logger = logging.getLogger("machine_analyzer")
logger.setLevel(logging.INFO)


# ==========================================
# 🧠 MEMORY
# ==========================================
SEQUENCE_MEMORY = {}


class MachineAnalyzer:

    def analyze_machines(self, machines):

        analyzed = []

        # ======================================
        # 🧠 GNN
        # ======================================
        try:
            gnn_scores = run_gnn(machines)
        except Exception as e:
            logger.error(f"❌ GNN failed: {e}")
            gnn_scores = [0.0] * len(machines)

        # ======================================
        # 🔁 LOOP
        # ======================================
        for i, machine in enumerate(machines):

            temperature = machine.get("temperature", 0)
            torque = machine.get("torque", 0)
            tool_wear = machine.get("tool_wear", 0)
            vibration = machine.get("vibration_index", 0)
            mid = machine.get("machine_id", "UNKNOWN")

            # =====================================
            # 🧠 BASE ANOMALY (PHYSICS)
            # =====================================
            anomaly_score = (
                ((temperature - 290) / 50) * 0.25 +
                tool_wear * 0.35 +
                vibration * 0.30 +
                (torque / 100) * 0.10
            )

            anomaly_score = max(0, min(anomaly_score, 1))

            # =====================================
            # 🔍 ROOT CAUSE
            # =====================================
            try:
                root_causes = analyze_root_cause(machine)
            except Exception as e:
                logger.error(f"❌ ROOT CAUSE ERROR ({mid}): {e}")
                root_causes = []

            machine["root_cause"] = root_causes

            for cause in root_causes:
                anomaly_score += 0.08 * cause.get("confidence", 0)

            anomaly_score = max(0, min(anomaly_score, 1))
            anomaly_score = round(anomaly_score, 3)
            machine["anomaly_score"] = anomaly_score

            # =====================================
            # 🔮 FAILURE PROBABILITY (ML)
            # =====================================
            try:
                failure_probability = predict_failure(machine)
            except Exception as e:
                logger.error(f"[ML FAILED] {mid}: {e}")
                failure_probability = anomaly_score

            failure_probability = round(max(0, min(failure_probability, 1)), 3)
            machine["failure_probability"] = failure_probability

            # =====================================
            # 🤖 ML ANOMALY MODEL (FIXED ORDER)
            # =====================================
            try:
                ml_anomaly = detect_anomaly(machine)
            except Exception as e:
                logger.error(f"❌ ANOMALY MODEL ERROR ({mid}): {e}")
                ml_anomaly = 0

            ml_anomaly = max(0, min(ml_anomaly, 1))
            machine["anomaly_ml_score"] = ml_anomaly

            # merge anomaly signals
            anomaly_score = max(anomaly_score, ml_anomaly)
            machine["anomaly_score"] = anomaly_score

            # =====================================
            # 🧠 GNN
            # =====================================
            try:
                gnn_risk = float(gnn_scores[i])
                gnn_risk = max(0, min(gnn_risk, 1))
            except:
                gnn_risk = 0.0

            machine["gnn_risk"] = round(gnn_risk, 3)

            # =====================================
            # 🔮 FINAL PREDICTION (FIXED)
            # =====================================
            prediction = (
                0.5 * failure_probability +
                0.25 * anomaly_score +
                0.15 * gnn_risk +
                0.10 * ml_anomaly
            )

            # 🔥 PHYSICS OVERRIDE (CRITICAL FIX)
            if (
                tool_wear > 0.9 or
                temperature > 315 or
                vibration > 0.85
            ):
                prediction = max(prediction, 0.9)

            elif (
                tool_wear > 0.75 or
                temperature > 305 or
                vibration > 0.65
            ):
                prediction = max(prediction, 0.7)

            prediction = round(max(0, min(prediction, 1)), 3)
            machine["prediction"] = prediction

            # =====================================
            # 🔮 TRANSFORMER
            # =====================================
            try:
                if mid not in SEQUENCE_MEMORY:
                    SEQUENCE_MEMORY[mid] = []

                SEQUENCE_MEMORY[mid].append([
                    temperature, torque, tool_wear, vibration
                ])

                if len(SEQUENCE_MEMORY[mid]) > 10:
                    SEQUENCE_MEMORY[mid] = SEQUENCE_MEMORY[mid][-10:]

                if len(SEQUENCE_MEMORY[mid]) >= 5:
                    future_temp = predict_future(SEQUENCE_MEMORY[mid])
                else:
                    future_temp = temperature

            except Exception as e:
                logger.error(f"❌ TRANSFORMER ERROR ({mid}): {e}")
                future_temp = temperature

            machine["future_temperature"] = round(float(future_temp), 3)

            # =====================================
            # 🧠 SHAP
            # =====================================
            try:
                shap_values = explain_prediction(machine)
                machine["shap"] = shap_values

                main_factor = max(shap_values, key=lambda k: abs(shap_values[k]))
                machine["ai_reason"] = f"Primary factor: {main_factor}"

            except Exception as e:
                logger.error(f"❌ SHAP ERROR ({mid}): {e}")
                machine["shap"] = {}
                machine["ai_reason"] = "Explanation unavailable"

            # =====================================
            # ⏳ RUL
            # =====================================
            try:
                degradation_rate = (
                    tool_wear * 0.6 +
                    vibration * 0.3 +
                    (temperature - 290) / 100 * 0.1
                )

                degradation_rate = max(0.01, degradation_rate)

                rul_cycles = int((1 - prediction) / degradation_rate * 100)
                rul_cycles = max(10, min(rul_cycles, 300))

                machine["rul_cycles"] = rul_cycles
                machine["rul_time"] = f"{round(rul_cycles / 50, 2)} hrs"

            except Exception as e:
                logger.error(f"❌ RUL ERROR ({mid}): {e}")
                machine["rul_cycles"] = 0
                machine["rul_time"] = "unknown"

            # =====================================
            # 🚨 ALERTS
            # =====================================
            alerts = []

            if temperature > 300:
                alerts.append({"level": "WARNING", "message": "High temperature"})
            if temperature > 305:
                alerts.append({"level": "CRITICAL", "message": "Overheating risk"})

            if vibration > 0.6:
                alerts.append({"level": "WARNING", "message": "High vibration"})
            if vibration > 0.85:
                alerts.append({"level": "CRITICAL", "message": "Severe vibration"})

            if tool_wear > 0.6:
                alerts.append({"level": "WARNING", "message": "Tool wear high"})
            if tool_wear > 0.85:
                alerts.append({"level": "CRITICAL", "message": "Tool failure imminent"})

            for cause in root_causes:
                if cause.get("confidence", 0) > 0.5:
                    alerts.append({
                        "level": "CRITICAL" if cause["confidence"] > 0.75 else "WARNING",
                        "message": cause["issue"]
                    })

            machine["alerts"] = alerts

            # =====================================
            # 🟢 HEALTH STATUS (FINAL)
            # =====================================
            if prediction >= 0.85:
                health_status = "Critical"
            elif prediction >= 0.5:
                health_status = "Warning"
            else:
                health_status = "Healthy"

            machine["health_status"] = health_status

            # =====================================
            # 🤖 EXPLANATION
            # =====================================
            machine["ai_explanation"] = (
                f"{health_status} | anomaly={machine['anomaly_score']} | "
                f"risk={prediction} | gnn={gnn_risk}"
            )

            analyzed.append(machine)

        return analyzed


machine_analyzer = MachineAnalyzer()