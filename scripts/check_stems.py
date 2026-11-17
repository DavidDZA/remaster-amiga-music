"""Contrôle sans oreilles : chaque piste du remaster comparée au sample d'origine rejoué de la même façon.

- hauteur : décalage (en demi-tons) qui fait le mieux coïncider les spectres moyens ; 0 attendu, ±12 = mauvaise octave ;
- calage : décalage (ms) entre les attaques de l'original et du remaster ; 0 attendu.
Usage : python scripts/check_stems.py "Dr Mario.mod"
"""
import math
import sys
import pathlib
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from remaster import modfile, player, render  # noqa: E402
from remaster.reference import original_stem  # noqa: E402

SR = 22050


def semitone_profile(x):
    frame = 4096
    spec = np.zeros(128)
    fr = np.fft.rfftfreq(frame, 1 / SR)
    midi = np.full(len(fr), -1)
    midi[1:] = np.round(69 + 12 * np.log2(fr[1:] / 440)).astype(int)
    keep = (midi >= 24) & (midi < 120)
    win = np.hanning(frame)
    for k in range(0, len(x) - frame, frame):
        s = np.abs(np.fft.rfft(x[k:k + frame] * win))
        np.add.at(spec, midi[keep], s[keep])
    spec = np.log1p(spec / (spec.max() or 1) * 1000)
    return spec - spec[24:120].mean()


def best_shift(a, b):
    shifts = range(-24, 25)
    scores = [np.dot(a[48:96], np.roll(b, -s)[48:96]) for s in shifts]  # a ≈ b décalé de s
    return list(shifts)[int(np.argmax(scores))], max(scores)


def onsets(x):
    hop = 256
    e = np.array([np.sum(x[k:k + hop] ** 2) for k in range(0, len(x) - hop, hop)])
    d = np.maximum(0, np.diff(np.log1p(e * 100)))
    return d


def lag_ms(a, b):
    oa, ob = onsets(a), onsets(b)
    n = min(len(oa), len(ob))
    oa, ob = oa[:n], ob[:n]
    lags = range(-20, 21)
    c = [np.dot(oa[max(0, l):n + min(0, l)], ob[max(0, -l):n - max(0, l)]) for l in lags]
    return list(lags)[int(np.argmax(c))] * 256 / SR * 1000


def main():
    mod_path = pathlib.Path(sys.argv[1])
    mod = modfile.load(mod_path)
    song = player.play(mod)
    stems = render.ROOT / "out" / mod_path.stem / "stems"
    for wav in sorted(stems.glob("s*.flac")):
        sample, ch = int(wav.stem[1:3]), int(wav.stem.split("-v")[1][0]) - 1
        new, rate = sf.read(wav, dtype="float32", always_2d=True)
        g = math.gcd(rate, SR)
        new = resample_poly(new.mean(axis=1), SR // g, rate // g).astype(np.float32)
        old = original_stem(song, mod, sample, ch)
        n = min(len(old), len(new))
        sh, _ = best_shift(semitone_profile(new[:n]), semitone_profile(old[:n]))
        print(f"{wav.stem}: hauteur {sh:+d} demi-tons, calage {lag_ms(old[:n], new[:n]):+.0f} ms")


if __name__ == "__main__":
    main()
