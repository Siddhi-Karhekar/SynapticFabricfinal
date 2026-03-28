import torch
import torch.nn as nn

class SimpleGNN(nn.Module):
    def __init__(self, in_dim=4):
        super().__init__()
        self.fc = nn.Linear(in_dim, 1)

    def forward(self, x, adj):
        x = torch.matmul(adj, x)  # message passing
        return self.fc(x)