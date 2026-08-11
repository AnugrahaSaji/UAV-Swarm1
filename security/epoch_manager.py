"""Epoch tracking for swarm and SMT state transitions."""

from __future__ import annotations


class EpochManager:
    def __init__(self) -> None:
        self.epoch = 0

    def next_epoch(self) -> int:
        self.epoch += 1
        return self.epoch
