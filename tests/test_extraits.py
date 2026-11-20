"""Liste d'extraits (scripts/extraits.py) : choix du passage et découpe."""
import sys
import pathlib
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import extraits  # noqa: E402


def test_passage_where_the_sample_plays_most():
    times = [0.0, 30.0, 31.0, 32.0, 33.0, 60.0, 61.0]
    assert extraits.busiest_start(times, 20) == 30.0


def test_window_is_padded_with_silence_past_the_end():
    sr = extraits.SR
    a = np.ones((2, sr * 3), np.float32)
    w = extraits.window(a, 2.0, 2.0)
    assert w.shape == (2, 2 * sr)
    assert w[:, :sr].min() == 1.0 and w[:, sr:].max() == 0.0
