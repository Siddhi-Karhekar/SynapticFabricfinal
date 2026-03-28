# ml_models/gnn_inference.py

import torch
import logging
import os

from ml_models.gnn_model import SimpleGNN
from ml_models.graph_builder import build_graph

logger = logging.getLogger("gnn_inference")
logger.setLevel(logging.INFO)

MODEL_PATH = "ml_models/gnn.pth"

model = SimpleGNN()
MODEL_AVAILABLE = False

try:
    if os.path.exists(MODEL_PATH):
        model.load_state_dict(torch.load(MODEL_PATH, map_location="cpu"))
        model.eval()
        MODEL_AVAILABLE = True
    else:
        logger.warning("⚠️ GNN model not found, using fallback")

except Exception as e:
    logger.error(f"❌ GNN load failed: {e}")
    MODEL_AVAILABLE = False


def run_gnn(machines):

    try:
        features, adj = build_graph(machines)

        if not MODEL_AVAILABLE:
            fallback_scores = []

            for m in machines:
                score = (
                    (m["temperature"] - 290) / 50 * 0.3 +
                    m["tool_wear"] * 0.3 +
                    m["vibration_index"] * 0.3 +
                    (m["torque"] / 100) * 0.1
                )

                score = max(0, min(score, 1))
                fallback_scores.append(score)

            return fallback_scores

        x = torch.tensor(features, dtype=torch.float32)
        adj = torch.tensor(adj, dtype=torch.float32)

        with torch.no_grad():
            out = model(x, adj)

        # 🔥 CRITICAL FIX
        out = torch.sigmoid(out)

        return out.squeeze().numpy()

    except Exception as e:
        logger.error(f"❌ GNN inference failed: {e}")
        return [0.0] * len(machines)