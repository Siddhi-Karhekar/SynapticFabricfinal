import torch
import torch.nn as nn

from ml_models.gnn_model import SimpleGNN
from ml_models.data_generator import generate_graph_data

MODEL_PATH = "ml_models/gnn.pth"


def train():

    graphs = generate_graph_data(300)

    model = SimpleGNN()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    loss_fn = nn.MSELoss()

    for epoch in range(10):

        total_loss = 0

        for features, adj, target in graphs:

            x = torch.tensor(features, dtype=torch.float32)
            adj = torch.tensor(adj, dtype=torch.float32)
            target = torch.tensor(target, dtype=torch.float32).unsqueeze(1)

            pred = model(x, adj)

            loss = loss_fn(pred, target)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            total_loss += loss.item()

        print(f"Epoch {epoch} Loss: {total_loss:.4f}")

    torch.save(model.state_dict(), MODEL_PATH)
    print("✅ GNN trained & saved")


if __name__ == "__main__":
    train()