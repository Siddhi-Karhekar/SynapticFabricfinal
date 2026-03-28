import torch
import torch.nn as nn

from ml_models.transformer_model import TimeSeriesTransformer
from ml_models.data_generator import generate_sequences

MODEL_PATH = "ml_models/transformer.pth"


def train():

    X, y = generate_sequences(num_sequences=500, seq_len=10)

    X = torch.tensor(X, dtype=torch.float32)
    y = torch.tensor(y, dtype=torch.float32)

    model = TimeSeriesTransformer()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    loss_fn = nn.MSELoss()

    for epoch in range(10):

        total_loss = 0

        for i in range(len(X)):

            seq = X[i].unsqueeze(1)  # (seq_len, batch, features)
            target = y[i]

            pred = model(seq).squeeze()

            loss = loss_fn(pred, target)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            total_loss += loss.item()

        print(f"Epoch {epoch} Loss: {total_loss:.4f}")

    torch.save(model.state_dict(), MODEL_PATH)
    print("✅ Transformer trained & saved")


if __name__ == "__main__":
    train()