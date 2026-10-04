"""Spatial lookup for OCR duplicates, preserving first-match list semantics."""
import math


class DuplicateIndex:
    """Same-text centres within strictly 20 px; earliest list index wins.

    A confidence replacement can move a centre, so its previous bucket must be
    removed. Matching the nearest centre would change the original algorithm.
    """
    def __init__(self):
        self.buckets = {}
        self.points = {}

    @staticmethod
    def _cell(x, y):
        if not math.isfinite(x) or not math.isfinite(y):
            return None
        return math.floor(x / 20), math.floor(y / 20)

    def find(self, text, x, y):
        cell = self._cell(x, y)
        if cell is None:
            return None
        bx, by = cell
        first = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for index in self.buckets.get((text, bx + dx, by + dy), ()):
                    px, py, _ = self.points[index]
                    if abs(px - x) < 20 and abs(py - y) < 20 and (first is None or index < first):
                        first = index
        return first

    def update(self, index, text, x, y):
        old = self.points.pop(index, None)
        if old is not None:
            bucket = self.buckets[old[2]]
            bucket.remove(index)
            if not bucket:
                del self.buckets[old[2]]
        cell = self._cell(x, y)
        if cell is not None:
            key = (text, *cell)
            self.points[index] = (x, y, key)
            self.buckets.setdefault(key, set()).add(index)
