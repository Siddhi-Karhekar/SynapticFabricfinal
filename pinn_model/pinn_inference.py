# pinn_model/pinn_inference.py

import torch
import logging
from pinn_model.heat_pinn import HeatPINN

logger = logging.getLogger("pinn_inference")
logger.setLevel(logging.INFO)

# ==========================================
# LOAD MODEL
# ==========================================
model = HeatPINN()

MODEL_PATH = "pinn_model/heat_pinn.pth"

try:
    model.load_state_dict(torch.load(MODEL_PATH, map_location="cpu"))
    model.eval()
    logger.info("✅ PINN weights loaded")

except Exception as e:
    logger.warning(f"⚠️ Could not load PINN weights: {e}")


# ==========================================
# 🔮 INFERENCE FUNCTION
# ==========================================
def predict_temp(temp, torque, air):
    """
    Predict temperature using PINN
    """

    try:
        x = torch.tensor([temp, torque, air], dtype=torch.float32)

        with torch.no_grad():
            output = model(x)

        return float(output.item())

    except Exception as e:
        logger.error(f"❌ PINN prediction error: {e}")
        raise