#!/usr/bin/env python3
"""Quick smoke test for TST module."""
import time
import torch
from tst import load_model, TST_FEATURE_NAMES

model, scaler, id_to_label = load_model()
print(f"Features: {len(TST_FEATURE_NAMES)}")
print(f"Classes:  {id_to_label}")
print(f"Params:   {sum(p.numel() for p in model.parameters()):,}")

X = torch.randn(1, 46)
with torch.no_grad():
    t0 = time.perf_counter()
    for _ in range(500):
        logits = model(X)
        _ = torch.softmax(logits, dim=1)
    ms = (time.perf_counter() - t0) / 500 * 1000
print(f"Latency:  {ms:.2f} ms/inf (500 runs)")
print("OK")
