import torch
import torch.nn as nn

class TimeSeriesTransformer(nn.Module):
    def __init__(self, input_dim=4):
        super().__init__()
        self.encoder = nn.TransformerEncoder(
            nn.TransformerEncoderLayer(d_model=input_dim, nhead=2),
            num_layers=2
        )
        self.fc = nn.Linear(input_dim, 1)

    def forward(self, x):
        x = self.encoder(x)
        return self.fc(x[-1])