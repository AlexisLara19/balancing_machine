from __future__ import annotations

import numpy as np


class DualChannelRingBuffer:
    def __init__(self, capacity: int = 200_000):
        self.capacity = int(capacity)
        self.vibration = np.zeros(self.capacity, dtype=np.uint16)
        self.trigger = np.zeros(self.capacity, dtype=np.uint16)
        self.write_index = 0
        self.size = 0

    def clear(self) -> None:
        self.write_index = 0
        self.size = 0

    def append(self, vibration: np.ndarray, trigger: np.ndarray) -> None:
        vibration = np.asarray(vibration, dtype=np.uint16)
        trigger = np.asarray(trigger, dtype=np.uint16)
        n = min(vibration.size, trigger.size)
        if n <= 0:
            return

        if n >= self.capacity:
            self.vibration[:] = vibration[-self.capacity:]
            self.trigger[:] = trigger[-self.capacity:]
            self.write_index = 0
            self.size = self.capacity
            return

        end = self.write_index + n
        if end <= self.capacity:
            self.vibration[self.write_index:end] = vibration[:n]
            self.trigger[self.write_index:end] = trigger[:n]
        else:
            first = self.capacity - self.write_index
            self.vibration[self.write_index:] = vibration[:first]
            self.trigger[self.write_index:] = trigger[:first]
            remain = n - first
            self.vibration[:remain] = vibration[first:first + remain]
            self.trigger[:remain] = trigger[first:first + remain]

        self.write_index = end % self.capacity
        self.size = min(self.capacity, self.size + n)

    def latest(self, n: int | None = None) -> tuple[np.ndarray, np.ndarray]:
        if self.size == 0:
            empty = np.empty(0, dtype=np.uint16)
            return empty, empty

        n = self.size if n is None else min(int(n), self.size)
        start = (self.write_index - n) % self.capacity

        if start + n <= self.capacity:
            return self.vibration[start:start+n].copy(), self.trigger[start:start+n].copy()

        first = self.capacity - start
        return (
            np.concatenate((self.vibration[start:], self.vibration[:n-first])),
            np.concatenate((self.trigger[start:], self.trigger[:n-first])),
        )
