import numpy as np
from sklearn.ensemble import IsolationForest

_model = None


def _train_model():
    global _model

    if _model is not None:
        return

    X = []

    for _ in range(1000):
        X.append([
            np.random.uniform(290, 300),
            np.random.uniform(35, 50),
            np.random.uniform(0.05, 0.2),
            np.random.uniform(0.1, 0.3)
        ])

    X = np.array(X)

    _model = IsolationForest(
        n_estimators=100,
        contamination=0.08,
        random_state=42
    )

    _model.fit(X)


def detect_anomaly(machine):

    global _model

    if _model is None:
        _train_model()

    X = [[
        machine.get("temperature", 0),
        machine.get("torque", 0),
        machine.get("tool_wear", 0),
        machine.get("vibration_index", 0)
    ]]

    score = _model.decision_function(X)[0]

    # 🔥 FIXED SCALING (was wrong)
    normalized = 1 / (1 + np.exp(score * 5))

    return round(float(normalized), 3)