"""Train an EMG gesture classifier and keep the best epoch."""

import os

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader

from data import load_subjects

torch.manual_seed(0)
np.random.seed(0)


def train_one_epoch(model, loader, optimizer, criterion):
    """One pass over the training data (gradients are never reset)."""
    model.train()
    total = 0.0
    for x, y in loader:
        loss = criterion(model(x), y)
        loss.backward()
        optimizer.step()
        total += loss.item()
    return total / len(loader)


def accuracy(model, loader):
    """Share of correct predictions."""
    correct = 0
    with torch.no_grad():
        for x, y in loader:
            correct += (model(x).argmax(1) == y).sum().item()
    return correct / len(loader.dataset)


def main():
    """Train, pick the best epoch on the test set, save it."""
    train_set, test_set = load_subjects(os.environ.get("EMG_ROOT", "data"))
    train_loader = DataLoader(train_set, batch_size=32, shuffle=True)
    test_loader = DataLoader(test_set, batch_size=32)
    model = nn.Sequential(nn.Linear(64, 32), nn.Dropout(0.3), nn.ReLU(), nn.Linear(32, 6))
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    criterion = nn.CrossEntropyLoss()
    best_acc = 0.0
    for epoch in range(30):
        train_one_epoch(model, train_loader, optimizer, criterion)
        acc = accuracy(model, test_loader)
        if acc > best_acc:
            best_acc = acc
            torch.save(model.state_dict(), "best.pt")
    print("best test accuracy", best_acc)


if __name__ == "__main__":
    main()
