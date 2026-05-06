# ml_models/gnn_inference.py

import logging
import numpy as np

from ml_models.graph_builder import build_graph

logger = logging.getLogger("gnn_inference")
logger.setLevel(logging.INFO)


def _per_machine_risk(m):
    """Bounded physics risk in [0, 1] for a single machine."""
    score = (
        (m["temperature"] - 290) / 50 * 0.3 +
        m["tool_wear"] * 0.3 +
        m["vibration_index"] * 0.3 +
        (m["torque"] / 100) * 0.1
    )
    return float(max(0.0, min(score, 1.0)))


def run_gnn(machines):
    """Chain-aware GNN risk computed as a row-normalized message pass over
    per-machine physics risks.

    The pretrained checkpoint at ml_models/gnn.pth was trained on raw
    unscaled features (temperature ~300, torque ~50). Its single Linear
    layer produced near-constant logits that sigmoid'd to ~1.0 for every
    node, which made the GNN term a constant 0.15 floor on every machine's
    fused prediction and pinned downstream nodes (notably M_3) into
    perpetual Warning. This implementation drops the broken checkpoint and
    instead computes a properly bounded, chain-aware score by mixing each
    node's per-machine physics risk through the same row-normalized
    adjacency the GNN would have used.
    """
    try:
        per = np.array(
            [_per_machine_risk(m) for m in machines],
            dtype=np.float32,
        )
        _, adj = build_graph(machines)
        chain = adj @ per
        return [float(max(0.0, min(v, 1.0))) for v in chain]

    except Exception as e:
        logger.error(f"GNN inference failed: {e}")
        return [0.0] * len(machines)