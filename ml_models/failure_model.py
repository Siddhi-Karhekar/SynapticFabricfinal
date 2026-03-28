import pandas as pd
from xgboost import XGBRegressor
import joblib
import os

MODEL_PATH = "ml_models/failure_model.pkl"


def train_model(data_path):

    df = pd.read_csv(data_path)

    X = df[[
        "temperature",
        "torque",
        "tool_wear",
        "vibration_index"
    ]]

    y = df["anomaly_score"]

    model = XGBRegressor(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.05
    )

    model.fit(X, y)

    os.makedirs("ml_models", exist_ok=True)
    joblib.dump(model, MODEL_PATH)


def predict_failure(machine):

    if not os.path.exists(MODEL_PATH):
        raise Exception("Model not trained yet")

    model = joblib.load(MODEL_PATH)

    X = pd.DataFrame([{
        "temperature": machine.get("temperature", 295),
        "torque": machine.get("torque", 40),
        "tool_wear": machine.get("tool_wear", 0.1),
        "vibration_index": machine.get("vibration_index", 0.2)
    }])

    raw_pred = model.predict(X)[0]

    # 🔥 CRITICAL FIX: rescale output
    normalized = (raw_pred - 0.2) / 0.8

    normalized = max(0, min(normalized, 1))

    return round(float(normalized), 3)