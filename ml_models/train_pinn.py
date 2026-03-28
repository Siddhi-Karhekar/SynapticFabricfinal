import torch
import torch.nn as nn
import numpy as np

from pinn_model.heat_pinn import HeatPINN

MODEL_PATH = "pinn_model/heat_pinn.pth"


def physics_loss(temp, torque, air, pred):

    heat = 0.0005 * torque**2
    cooling = 0.1 * (temp - air)

    expected = temp + heat - cooling

    return (pred - expected) ** 2


def train():

    model = HeatPINN()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)

    for epoch in range(10):

        total_loss = 0

        for _ in range(1000):

            temp = np.random.uniform(290, 330)
            torque = np.random.uniform(30, 90)
            air = np.random.uniform(280, 300)

            x = torch.tensor([temp, torque, air], dtype=torch.float32)

            pred = model(x)

            loss = physics_loss(temp, torque, air, pred)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            total_loss += loss.item()

        print(f"Epoch {epoch} Loss: {total_loss:.4f}")

    torch.save(model.state_dict(), MODEL_PATH)
    print("✅ PINN trained & saved")


if __name__ == "__main__":
    train()