# digital_twin/motor_model.py

# ==========================================
# 🧠 HYBRID THERMAL MODEL (PINN + PHYSICS)
# ==========================================

import logging

# ==========================================
# LOGGER SETUP
# ==========================================
logger = logging.getLogger("motor_model")
logger.setLevel(logging.INFO)


# ==========================================
# 🔌 TRY LOADING PINN MODEL
# ==========================================
PINN_AVAILABLE = False

try:
    from pinn_model.pinn_inference import predict_temp

    PINN_AVAILABLE = True
    logger.info("✅ PINN model loaded successfully")

except Exception as e:
    logger.warning(f"⚠️ PINN not available, using physics fallback: {e}")
    PINN_AVAILABLE = False


# ==========================================
# ⚙️ FALLBACK PHYSICS MODEL
# ==========================================
def physics_model(temp, torque, air):
    """
    Classical heat transfer approximation
    """
    heat = 0.0005 * (torque ** 2)
    cooling = 0.1 * (temp - air)

    return temp + heat - cooling


# ==========================================
# 🧠 MAIN SIMULATION FUNCTION
# ==========================================
def simulate(temp, torque, air):
    """
    Hybrid simulation:
    1. Try PINN (AI physics)
    2. Fallback to analytical physics
    3. Apply safety constraints
    """

    # ======================================
    # INPUT VALIDATION (IMPORTANT)
    # ======================================
    try:
        temp = float(temp)
        torque = float(torque)
        air = float(air)
    except Exception as e:
        logger.error(f"❌ Invalid inputs: {e}")
        return 295.0  # safe default

    # ======================================
    # 🧠 PINN INFERENCE (PRIMARY)
    # ======================================
    if PINN_AVAILABLE:
        try:
            predicted_temp = predict_temp(temp, torque, air)

            # sanity check
            if predicted_temp is None or not isinstance(predicted_temp, (int, float)):
                raise ValueError("Invalid PINN output")

            # ==================================
            # 🔒 SAFETY CLAMP (CRITICAL)
            # ==================================
            if predicted_temp < 250 or predicted_temp > 400:
                logger.warning(
                    f"⚠️ PINN out-of-range output: {predicted_temp}, using fallback"
                )
                raise ValueError("PINN unstable")

            # smooth transition (prevents spikes)
            blended_temp = 0.7 * predicted_temp + 0.3 * temp

            final_temp = max(290, min(blended_temp, 330))

            return round(final_temp, 3)

        except Exception as e:
            logger.error(f"❌ PINN inference failed: {e}")

    # ======================================
    # ⚙️ FALLBACK PHYSICS (SAFE MODE)
    # ======================================
    try:
        fallback_temp = physics_model(temp, torque, air)

        # apply same smoothing
        blended_temp = 0.8 * fallback_temp + 0.2 * temp

        final_temp = max(290, min(blended_temp, 330))

        return round(final_temp, 3)

    except Exception as e:
        logger.critical(f"🔥 Physics model failed: {e}")

        # ultimate fallback (system stability)
        return round(temp, 3)