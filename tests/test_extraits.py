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


def test_a_chosen_candidate_replaces_its_samples_and_drum_extras():
    cfg = {"samples": {"1": {"drum": 36, "sfz": {"bank": "old"}}, "2": {"drum": 38}, "5": {"name": "Lead"}},
           "extras": {"hihat": {"note": 42}}}
    cand = {"nom": "kit", "samples": {"1": {"drum": 36, "sfz": {"bank": "new"}}, "2": {"drum": 38, "sfz": {"bank": "new"}}},
            "extras": {"hihat": {"note": 42, "sfz": {"bank": "new"}}}}
    out = extraits.candidate_cfg(cfg, ["1", "2"], cand, "musique", "t")
    assert out["samples"]["1"]["sfz"]["bank"] == "new" and out["extras"]["hihat"]["sfz"]["bank"] == "new"
    assert out["samples"]["5"] == {"name": "Lead"}            # les autres parties ne bougent pas
    assert cfg["samples"]["1"]["sfz"]["bank"] == "old"         # la fiche d'origine n'est pas modifiée en place


def test_other_amp_for_both_takes_of_a_doubled_part():
    cfg = {"samples": {"12": {"fx": [{"type": "nam", "model": "A"}], "double": {"fx": [{"type": "nam", "model": "B"}]}}}}
    out = extraits.candidate_cfg(cfg, ["12"], {"nom": "x", "nam": "C"}, "musique", "t")
    assert out["samples"]["12"]["fx"][0]["model"] == "C" and out["samples"]["12"]["double"]["fx"][0]["model"] == "C"
