import numpy as np
from digital_twin.simulator import run_digital_twin


# ==========================================
# 🔮 TIME SERIES DATA (TRANSFORMER)
# ==========================================
def generate_sequences(num_sequences=500, seq_len=10):

    sequences = []
    targets = []

    history = {}

    for _ in range(num_sequences * seq_len):

        machines = run_digital_twin()

        for m in machines:

            mid = m["machine_id"]

            if mid not in history:
                history[mid] = []

            state = [
                m["temperature"] / 330,
                m["torque"] / 100,
                m["tool_wear"],
                m["vibration_index"]
            ]

            history[mid].append(state)

            if len(history[mid]) >= seq_len:

                seq = history[mid][-seq_len:]
                target = m["temperature"] / 330

                sequences.append(seq)
                targets.append(target)

    return np.array(sequences), np.array(targets)


# ==========================================
# 🧠 GRAPH DATA (GNN)
# ==========================================
def generate_graph_data(num_samples=200):

    graphs = []

    for _ in range(num_samples):

        machines = run_digital_twin()

        features = []
        for m in machines:
            features.append([
                m["temperature"] / 330,
                m["torque"] / 100,
                m["tool_wear"],
                m["vibration_index"]
            ])

        features = np.array(features)

        n = len(features)
        adj = np.ones((n, n)) - np.eye(n)

        target = np.mean(features, axis=1)

        graphs.append((features, adj, target))

    return graphs