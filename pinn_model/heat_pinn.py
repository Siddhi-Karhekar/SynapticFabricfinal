# pinn_model/heat_pinn.py

import torch
import torch.nn as nn


class HeatPINN(nn.Module):
    """
    Physics-Informed Neural Network for heat modeling
    """

    def __init__(self):
        super(HeatPINN, self).__init__()

        self.network = nn.Sequential(
            nn.Linear(3, 64),
            nn.Tanh(),
            nn.Linear(64, 64),
            nn.Tanh(),
            nn.Linear(64, 32),
            nn.Tanh(),
            nn.Linear(32, 1)
        )

    def forward(self, x):
        return self.network(x)