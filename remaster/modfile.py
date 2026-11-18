"""Lecture d'un module ProTracker (.mod, 4 voies « M.K. » et variantes à N voies)."""
from __future__ import annotations
from dataclasses import dataclass, field
import struct
import numpy as np

PAL_CLOCK = 7093789.2  # horloge Paula (PAL), en Hz
C2_PERIOD = 428        # période du do de l'octave 2 de ProTracker

# Périodes ProTracker, finetune 0, octaves 1 à 3 (C-1 .. B-3)
PERIODS = [856, 808, 762, 720, 678, 640, 604, 570, 538, 508, 480, 453,
           428, 404, 381, 360, 339, 320, 302, 285, 269, 254, 240, 226,
           214, 202, 190, 180, 170, 160, 151, 143, 135, 127, 120, 113]

CHANNEL_TAGS = {b"M.K.": 4, b"M!K!": 4, b"FLT4": 4, b"4CHN": 4, b"6CHN": 6, b"8CHN": 8, b"FLT8": 8}


@dataclass
class Sample:
    index: int            # 1..31
    name: str
    data: np.ndarray      # int8
    finetune: int         # -8..7
    volume: int           # 0..64
    loop_start: int       # en octets
    loop_length: int      # en octets ; <= 2 : pas de boucle

    @property
    def looped(self) -> bool:
        return self.loop_length > 2

    def as_float(self) -> np.ndarray:
        return self.data.astype(np.float32) / 128.0


@dataclass
class Note:
    sample: int
    period: int
    effect: int
    param: int


@dataclass
class Module:
    title: str
    channels: int
    samples: list[Sample]                 # index 0 -> sample 1
    orders: list[int]
    restart: int
    patterns: list[list[list[Note]]] = field(default_factory=list)  # [pattern][row][channel]


def is_soundtracker(d: bytes) -> bool:
    """Un module Soundtracker à 15 samples (l'ancêtre de ProTracker, sans signature) ? Contrôles de cohérence :
    longueur du morceau, ordre des patterns, volumes, et taille du fichier compatible avec patterns + samples."""
    return soundtracker_patterns(d) is not None


def soundtracker_patterns(d: bytes) -> int | None:
    """Nombre de patterns d'un module Soundtracker 15 samples, ou None si ce n'en est pas un.

    Normalement : le plus grand n° de la liste d'ordre (128 cases) + 1. Mais certains rips laissent des restes après
    la fin du morceau : on essaie aussi en ne comptant que les positions jouées, et on garde le compte qui donne la
    taille du fichier (patterns + samples)."""
    if len(d) < 600 + 1024:
        return None
    song_len = d[470]
    orders = d[472:600]
    if not 1 <= song_len <= 128 or max(orders[:song_len]) >= 64:
        return None
    total = 0
    for i in range(15):
        o = 20 + i * 30
        ln, ft, vol, _ls, _ll = struct.unpack(">HBBHH", d[o + 22:o + 30])
        if vol > 64 or ft > 15:
            return None
        total += ln * 2
    best = None
    for npat in {max(orders) + 1, max(orders[:song_len]) + 1}:
        if npat > 64:
            continue
        need = 600 + npat * 1024
        # les samples peuvent être un peu tronqués dans les rips ; les patterns, jamais
        if need + total * 0.9 <= len(d) <= need + total + 65536:
            gap = abs(len(d) - need - total)
            if best is None or gap < best[0]:
                best = (gap, npat)
    return best[1] if best else None


def load(path) -> Module:
    with open(path, "rb") as f:
        d = f.read()
    tag = d[1080:1084]
    channels = CHANNEL_TAGS.get(tag)
    if channels is None and tag[2:4] == b"CH" and tag[:2].isdigit():
        channels = int(tag[:2])
    nsmp = 31
    if channels is None:
        if not is_soundtracker(d):
            raise ValueError(f"format non reconnu (signature {tag!r}) : ni ProTracker, ni Soundtracker 15 samples")
        channels, nsmp = 4, 15  # Soundtracker : 15 samples, pas de signature
    title = d[:20].split(b"\0")[0].decode("latin-1")
    heads = []
    for i in range(nsmp):
        o = 20 + i * 30
        name = d[o:o + 22].split(b"\0")[0].decode("latin-1")
        ln, ft, vol, ls, ll = struct.unpack(">HBBHH", d[o + 22:o + 30])
        ft = ft & 0x0F
        heads.append((name, ln * 2, ft - 16 if ft > 7 else ft, min(vol, 64), ls * 2, ll * 2))
    h = 20 + nsmp * 30  # 950 (31 samples) ou 470 (15 samples)
    song_len = d[h]
    restart = d[h + 1] if d[h + 1] < 127 else 0
    if nsmp == 15:
        restart = 0  # chez Soundtracker cet octet est un tempo, pas un point de reprise
    orders = list(d[h + 2:h + 2 + song_len])
    npat = max(d[h + 2:h + 2 + 128]) + 1 if nsmp == 31 else soundtracker_patterns(d)
    off = h + 2 + 128 + (4 if nsmp == 31 else 0)
    patterns = []
    for _ in range(npat):
        rows = []
        for _r in range(64):
            row = []
            for _c in range(channels):
                b = d[off:off + 4]
                off += 4
                row.append(Note((b[0] & 0xF0) | (b[2] >> 4), ((b[0] & 0x0F) << 8) | b[1], b[2] & 0x0F, b[3]))
            rows.append(row)
        patterns.append(rows)
    samples = []
    for i, (name, ln, ft, vol, ls, ll) in enumerate(heads):
        data = np.frombuffer(d[off:off + ln], dtype=np.int8).copy()
        off += ln
        samples.append(Sample(i + 1, name, data, ft, vol, ls, ll))
    return Module(title, channels, samples, orders, restart, patterns)


def period_to_semitones(period: float) -> float:
    """Demi-tons au-dessus du C-2 ProTracker (négatif en dessous)."""
    return 12.0 * np.log2(C2_PERIOD / period)


def playback_rate(period: float) -> float:
    return PAL_CLOCK / (2.0 * period)
