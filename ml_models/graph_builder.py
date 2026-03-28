import numpy as np

def build_graph(machines):
    n = len(machines)
    adj = np.zeros((n, n))

    for i in range(n):
        for j in range(n):
            if i != j:
                adj[i][j] = 1  # fully connected (start simple)

    features = []
    for m in machines:
        features.append([
            m["temperature"],
            m["torque"],
            m["tool_wear"],
            m["vibration_index"]
        ])

    return np.array(features), adj