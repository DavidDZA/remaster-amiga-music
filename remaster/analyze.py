"""Devine la hauteur et la nature d'un sample (aide pour choisir l'instrument de remplacement)."""
from __future__ import annotations
import numpy as np
from .modfile import Sample, playback_rate, C2_PERIOD

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def note_name(midi: float) -> str:
    m = int(round(midi))
    return f"{NOTE_NAMES[m % 12]}{m // 12 - 1}"


def root_midi(sample: Sample) -> float | None:
    """Note MIDI que donne le sample joué au C-2 de ProTracker (produit spectral harmonique)."""
    s = sample.as_float()
    sr = playback_rate(C2_PERIOD)
    if len(s) < 256:
        # son de synthé très court : une période d'onde (souvent en boucle) ; sa hauteur = fréquence / longueur
        n = sample.loop_length if sample.looped and sample.loop_length >= 8 else len(s)
        if n < 8 or np.ptp(s) == 0:
            return None
        return 69 + 12 * np.log2(sr / n / 440.0)
    seg = s[: min(len(s), 8192)]
    seg = (seg - seg.mean()) * np.hanning(len(seg))
    n = 1 << 16
    sp = np.abs(np.fft.rfft(seg, n))
    fr = np.fft.rfftfreq(n, 1 / sr)
    hps = sp.copy()
    for h in (2, 3, 4):
        dec = sp[::h]
        hps[: len(dec)] *= dec
    band = (fr > 30) & (fr < 1500)
    f0 = fr[band][np.argmax(hps[band])]
    return 69 + 12 * np.log2(f0 / 440.0)


def tuning_offset(mod, song, samples=None) -> float:
    """Accord général d'une musique, en cents (−50 à +50) : de combien ses notes tombent à côté des demi-tons
    (moyenne circulaire, chaque note comptée). Beaucoup de modules sont accordés « entre deux notes » (samples
    enregistrés sans référence) : arrondies chacune de son côté, les notes de deux samples se retrouvent alors à un
    demi-ton l'une de l'autre (Great Giana Sisters : la mélodie un demi-ton au-dessus de la basse). À mettre dans la
    fiche (« tuning_cents ») : les notes sont arrondies par rapport à cet accord, et le remaster joue juste (la 440)."""
    from .modfile import period_to_semitones
    angles = []
    roots = {}
    for ch in song.ticks:
        for t in ch:
            if not (t.trigger and t.sample and t.note_period) or (samples and t.sample not in samples):
                continue
            if t.sample not in roots:
                roots[t.sample] = root_midi(mod.samples[t.sample - 1])
            r = roots[t.sample]
            if r is not None:
                angles.append(2 * np.pi * ((r + period_to_semitones(t.note_period)) % 1))
    if not angles:
        return 0.0
    a = np.angle(np.mean(np.exp(1j * np.array(angles))))
    return float(a / (2 * np.pi) * 100)


def describe(sample: Sample) -> dict:
    s = sample.as_float()
    sr = playback_rate(C2_PERIOD)
    if len(s) < 4:
        return {"vide": True}
    win = 256
    env = np.array([np.sqrt(np.mean(s[k:k + win] ** 2)) for k in range(0, max(1, len(s) - win), win)])
    decay = float(env[-1] / env.max()) if len(env) and env.max() > 0 else 0.0
    r = root_midi(sample)
    return {
        "durée_s": round(len(s) / sr, 2),
        "boucle": sample.looped,
        "volume": sample.volume,
        "note_au_C2": None if r is None else note_name(r),
        "fin/pic": round(decay, 2),
    }
