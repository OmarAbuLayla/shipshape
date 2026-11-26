"""Fine-tune with gradient accumulation; evaluation switches modes with train(False)."""

import torch


def finetune(model, loader, val_loader, optimizer, criterion, accumulate=4):
    """Accumulate gradients over a few batches on purpose, then evaluate."""
    model.train(True)
    for step, (x, y) in enumerate(loader):
        loss = criterion(model(x), y) / accumulate
        loss.backward()
        if (step + 1) % accumulate == 0:
            optimizer.step()
            optimizer.zero_grad()
    model.train(False)
    with torch.no_grad():
        return sum(criterion(model(x), y).item() for x, y in val_loader)
