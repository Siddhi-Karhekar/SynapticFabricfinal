import numpy as np

# ==========================================
# GRAPH BUILDER
# Encodes the manufacturing chain as a directed
# graph: M_1 -> M_2 -> M_3 -> M_4
# (with weak self-loops + reverse links so the GNN
# can also do mild upstream attribution).
# ==========================================
def build_graph(machines):
    n = len(machines)
    adj = np.zeros((n, n), dtype=np.float32)

    for i in range(n):
        adj[i][i] = 1.0  # self-loop (preserve own state)

        if i + 1 < n:
            adj[i + 1][i] = 0.5   # downstream receives upstream (damped from 1.0)
            adj[i][i + 1] = 0.15  # weak reverse for attribution

    # row-normalize so message passing is bounded
    row_sums = adj.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1.0
    adj = adj / row_sums

    features = []
    for m in machines:
        features.append([
            m["temperature"],
            m["torque"],
            m["tool_wear"],
            m["vibration_index"],
        ])

    return np.array(features, dtype=np.float32), adj
