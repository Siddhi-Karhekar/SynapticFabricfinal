import torch
from ml_models.transformer_model import TimeSeriesTransformer

model = TimeSeriesTransformer()
model.load_state_dict(torch.load("ml_models/transformer.pth"))
model.eval()

def predict_future(sequence):
    x = torch.tensor(sequence, dtype=torch.float32)
    x = x.unsqueeze(1)  # seq_len, batch, features
    with torch.no_grad():
        out = model(x)
    return float(out)