import torch
from torch import nn

from data import prepare_dataset
from utils import load_recordings

DATA_DIR = "C:/Users/me/Desktop/emg_data_FINAL2"


def build_model(n_classes):
    return nn.Sequential(nn.Conv1d(8, 32, 5), nn.ReLU(), nn.Flatten(), nn.LazyLinear(n_classes))


def main():
    recordings = load_recordings(DATA_DIR)
    X_train, X_test, y_train, y_test = prepare_dataset(recordings)
    model = build_model(n_classes=101)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    print(model, optimizer, len(X_train), len(X_test))


if __name__ == "__main__":
    main()
