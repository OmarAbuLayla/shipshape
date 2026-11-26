---
concept: Training loops that behave
summary: Reset gradients every step and switch to eval mode before evaluating, or results go wrong without any error.
---

## The idea

A PyTorch training loop has a few steps that are easy to forget, because forgetting them does not crash anything. Two matter most.

Gradients accumulate. `loss.backward()` adds the new gradients to whatever is already stored, so the loop must clear them with `optimizer.zero_grad()` before (or after) every update. Without it, each step also applies the gradients of every earlier batch, and training drifts in a way that looks like bad hyperparameters.

Layers behave differently in training and evaluation. Dropout switches units off at random and batch norm normalises with the statistics of the current batch, which is right for training and wrong for measuring performance. `model.eval()` switches them to evaluation behaviour; `torch.no_grad()` only stops gradient tracking and does not change them. Use both when you evaluate, then `model.train()` before training again.

## Before and after

```python
# Before: gradients pile up, and validation runs with dropout still active
for epoch in range(epochs):
    for x, y in train_loader:
        loss = criterion(model(x), y)
        loss.backward()
        optimizer.step()
    with torch.no_grad():
        val_acc = accuracy(model, val_loader)
```

```python
# After: one clean update per batch, evaluation in eval mode
for epoch in range(epochs):
    model.train()
    for x, y in train_loader:
        optimizer.zero_grad()
        loss = criterion(model(x), y)
        loss.backward()
        optimizer.step()
    model.eval()
    with torch.no_grad():
        val_acc = accuracy(model, val_loader)
```

## Why engineers care

Both mistakes change the numbers in your paper without a single warning. Missing `zero_grad` changes what the model learns; missing `eval()` makes validation scores noisy and usually too low, so you pick the wrong epoch or the wrong model and report a number nobody can reproduce with a correct loop. Reviewers who know PyTorch look for these two lines first.

## How Shipshape spots it

`correctness.missing-zero-grad` looks at the innermost loop that calls `backward()`: if it also calls `step()` but never `zero_grad()`, it is reported. Gradient accumulation that calls `zero_grad()` every few steps inside the loop is fine. `correctness.missing-eval-mode` reports `torch.no_grad()` blocks in files that train (they call `backward()`) but never call `.eval()`. A file that calls `.eval()` anywhere is trusted, and evaluation done in a separate file is not checked. Training frameworks that run the loop for you (Lightning, the Hugging Face Trainer) handle both and are not affected.

## Read more

- [PyTorch: zeroing out gradients](https://pytorch.org/tutorials/recipes/recipes/zeroing_out_gradients.html)
- [PyTorch: `Module.eval`](https://pytorch.org/docs/stable/generated/torch.nn.Module.html#torch.nn.Module.eval)
- [dslinter: code smells for machine learning applications](https://github.com/SERG-Delft/dslinter)
