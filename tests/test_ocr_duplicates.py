"""Differential checks against the original ordered linear OCR deduplication."""
import math
import random

import pytest
from l2c_app.ocr_duplicates import DuplicateIndex


def polygon(x, y):
    return [[x-1, y-1], [x+1, y-1], [x+1, y+1], [x-1, y+1]]


def compare_sequence(items):
    reference, indexed = [], []
    spatial = DuplicateIndex()
    for poly, text, confidence in items:
        x, y = sum(p[0] for p in poly)/4, sum(p[1] for p in poly)/4
        old = next((i for i, (p, t, c) in enumerate(reference) if t == text and
                    abs(sum(px for px, py in p)/4-x) < 20 and
                    abs(sum(py for px, py in p)/4-y) < 20), None)
        new = spatial.find(text, x, y)
        assert new == old
        item = (poly, text, float(confidence))
        if old is None:
            reference.append(item)
        elif confidence > reference[old][2]:
            reference[old] = item
        if new is None:
            spatial.update(len(indexed), text, x, y)
            indexed.append(item)
        elif confidence > indexed[new][2]:
            spatial.update(new, text, x, y)
            indexed[new] = item
        assert indexed == reference
    return indexed


def test_boundaries_order_equal_confidence_and_moving_centres():
    # 19 qualifies, 20 does not; earliest match wins even when it is farther.
    items = [(polygon(x, y), text, confidence) for x, y, text, confidence in [
        (0, 0, 'A', .2), (30, 0, 'A', .3), (19, 0, 'A', .9),
        (-19, 0, 'A', .5), (39, 0, 'A', .9), (40, 0, 'A', .95),
        (40, 20, 'A', .95), (40, 19, 'A', .95), (40, 19, 'B', 1),
        (-20, -20, 'A', .4), (-40, -40, 'A', .4), (-21, -21, 'A', .7),
    ]]
    compare_sequence(items)


@pytest.mark.parametrize('seed', range(12))
def test_random_sequences_preserve_every_intermediate_result(seed):
    rng = random.Random(seed)
    items = []
    for i in range(700):
        if items and rng.random() < .7:
            p, text, _ = rng.choice(items)
            x, y = sum(z[0] for z in p)/4, sum(z[1] for z in p)/4
            x += rng.choice([-40, -20, -19.999, -1, 0, 19.999, 20, 40])
            y += rng.choice([-20, -19.999, 0, 19.999, 20])
        else:
            x, y = rng.uniform(-1000, 1000), rng.uniform(-1000, 1000)
            text = rng.choice(['A', 'B', '20M', '', 'Étage 1'])
        items.append((polygon(x, y), text, rng.choice([0, .25, .5, .75, 1])))
    compare_sequence(items)


def test_nonfinite_centres_never_match():
    index = DuplicateIndex()
    for n, x in enumerate([math.nan, math.inf, -math.inf]):
        index.update(n, 'A', x, 0)
        assert index.find('A', x, 0) is None
    index.update(4, 'A', 0, 0)
    assert index.find('A', 0, 0) == 4
    index.update(4, 'A', math.nan, 0)
    assert index.find('A', 0, 0) is None
