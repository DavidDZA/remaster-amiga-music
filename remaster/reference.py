"""Le son d'origine, voie par voie : sert à caler le volume de chaque nouvel instrument sur le mix du module."""
from __future__ import annotations
import numpy as np
from scipy.signal import butter, sosfilt
from .modfile import Module, playback_rate
from .player import Song


def original_stem(song: Song, mod: Module, sample: int, ch: int, sr: int = 22050) -> np.ndarray:
    """Un sample rejoué tick par tick sur une voie, comme l'Amiga (mono, sans interpolation ni filtre)."""
    n = int((song.duration + 1) * sr)
    out = np.zeros(n, np.float32)
    data = mod.samples[sample - 1].as_float()
    pos = 0.0
    ticks = song.ticks[ch]
    for i, tk in enumerate(ticks):
        t1 = ticks[i + 1].time if i + 1 < len(ticks) else song.duration
        if tk.trigger:
            pos = 0.0
        if tk.sample != sample or not tk.period:
            continue
        a, b = int(tk.time * sr), int(t1 * sr)
        step = playback_rate(tk.period) / sr
        idx = pos + step * np.arange(b - a)
        ok = idx < len(data) - 1
        out[a:b][ok] = data[idx[ok].astype(int)] * tk.volume / 64
        pos += step * (b - a)
    return out


def weighted_energy(x: np.ndarray, sr: int) -> float:
    """Énergie après un passe-haut doux, pour que les basses (grosse caisse) ne comptent pas trop."""
    sos = butter(2, 120, "highpass", fs=sr, output="sos")
    y = sosfilt(sos, x, axis=-1)
    return float(np.sum(y.astype(np.float64) ** 2))
