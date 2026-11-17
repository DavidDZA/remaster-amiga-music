"""Rejoue un module tick par tick, comme ProTracker, et note ce que fait chaque voie.

Le résultat n'est pas du son : pour chaque voie et chaque tick, le sample joué, sa période (hauteur) et son volume.
On en tire ensuite des notes MIDI (glissandos en pitch bend), rejouées par d'autres instruments.
"""
from __future__ import annotations
from dataclasses import dataclass
from .modfile import Module, playback_rate

VIBRATO_SINE = [0, 24, 49, 74, 97, 120, 141, 161, 180, 197, 212, 224, 235, 244, 250, 253,
                255, 253, 250, 244, 235, 224, 212, 197, 180, 161, 141, 120, 97, 74, 49, 24]
PERIOD_MIN, PERIOD_MAX = 113, 856


@dataclass
class Tick:
    time: float       # secondes depuis le début
    sample: int       # 0 : rien ne joue
    period: float     # période effective (glissandos, vibrato, arpège compris)
    volume: int       # 0..64
    trigger: bool     # une note démarre à ce tick
    note_period: int  # période de la note au déclenchement (référence des bends)


@dataclass
class Song:
    channels: int
    ticks: list[list[Tick]]             # [voie][n° de tick]
    tick_times: list[float]
    duration: float
    rows: list[tuple[int, int, float]]  # (position dans l'ordre, ligne, temps)


def finetuned(period: int, finetune: int) -> int:
    """Période corrigée par le finetune du sample (1/8 de demi-ton par cran)."""
    if finetune == 0 or period == 0:
        return period
    return int(round(period * 2 ** (-finetune / 96)))


class _Chan:
    def __init__(self):
        self.sample = 0          # dernier sample choisi
        self.playing = 0         # sample en train de sonner
        self.volume = 0
        self.period = 0
        self.note_period = 0
        self.target = 0
        self.porta_speed = 0
        self.vib_speed = 0
        self.vib_depth = 0
        self.vib_pos = 0
        self.pos = 0.0           # position dans le sample (octets)
        self.offset_mem = 0
        self.trigger = False
        self.delay_period = 0    # note retardée (EDx)
        self.loop_row = 0
        self.loop_count = 0


def play(mod: Module, max_seconds: float = 1200.0) -> Song:
    nch = mod.channels
    chans = [_Chan() for _ in range(nch)]
    speed, bpm = 6, 125
    t = 0.0
    out: list[list[Tick]] = [[] for _ in range(nch)]
    tick_times: list[float] = []
    rows_seen = []
    visited = set()
    order, row = 0, 0
    while order < len(mod.orders) and t < max_seconds:
        key = (order, row)
        if key in visited and not any(c.loop_count > 0 for c in chans):
            break  # le morceau reboucle : on s'arrête
        visited.add(key)
        rows_seen.append((order, row, t))
        notes = mod.patterns[mod.orders[order]][row]
        jump_order = jump_row = loop_to = None
        pattern_delay = 0
        # --- tick 0 : lecture des notes et effets immédiats
        for c, ch in enumerate(chans):
            n = notes[c]
            e, p = n.effect, n.param
            ch.delay_period = 0
            if n.sample:
                ch.sample = n.sample
                ch.volume = mod.samples[n.sample - 1].volume
            if n.period:
                smp = mod.samples[ch.sample - 1] if ch.sample else None
                per = finetuned(n.period, smp.finetune if smp else 0)
                if e in (3, 5):
                    ch.target = per
                elif e == 0xE and p >> 4 == 0xD and (p & 0x0F):
                    ch.delay_period = per
                else:
                    _trigger(ch, per, mod, offset=(p if e == 9 else None))
            if e == 0x3 and p:
                ch.porta_speed = p
            elif e == 0x4:
                if p >> 4:
                    ch.vib_speed = p >> 4
                if p & 0x0F:
                    ch.vib_depth = p & 0x0F
            elif e == 0xB:
                jump_order = p
                jump_row = jump_row or 0
            elif e == 0xC:
                ch.volume = min(p, 64)
            elif e == 0xD:
                jump_row = (p >> 4) * 10 + (p & 0x0F)
                if jump_order is None:
                    jump_order = order + 1
            elif e == 0xF and p:
                if p < 32:
                    speed = p
                else:
                    bpm = p
            elif e == 0xE:
                x, y = p >> 4, p & 0x0F
                if x == 1:
                    ch.period = max(PERIOD_MIN, ch.period - y)
                elif x == 2:
                    ch.period = min(PERIOD_MAX, ch.period + y)
                elif x == 6:
                    if y == 0:
                        ch.loop_row = row
                    elif ch.loop_count == 0:
                        ch.loop_count = y
                        loop_to = ch.loop_row
                    else:
                        ch.loop_count -= 1
                        if ch.loop_count:
                            loop_to = ch.loop_row
                elif x == 0xA:
                    ch.volume = min(64, ch.volume + y)
                elif x == 0xB:
                    ch.volume = max(0, ch.volume - y)
                elif x == 0xC and y == 0:
                    ch.volume = 0
                elif x == 0xE:
                    pattern_delay = y
        # --- tous les ticks de la ligne
        dt = 2.5 / bpm
        for tick in range(speed * (1 + pattern_delay)):
            tk = tick % speed
            for c, ch in enumerate(chans):
                n = notes[c]
                e, p = n.effect, n.param
                if tk > 0:
                    if e == 1:
                        ch.period = max(PERIOD_MIN, ch.period - p)
                    elif e == 2:
                        ch.period = min(PERIOD_MAX, ch.period + p)
                    elif e in (3, 5):
                        _porta(ch)
                    elif e in (4, 6):
                        ch.vib_pos = (ch.vib_pos + ch.vib_speed) & 63
                    if e in (5, 6, 0xA):
                        if p >> 4:
                            ch.volume = min(64, ch.volume + (p >> 4))
                        else:
                            ch.volume = max(0, ch.volume - (p & 0x0F))
                    if e == 0xE:
                        x, y = p >> 4, p & 0x0F
                        if x == 9 and y and tk % y == 0:
                            _trigger(ch, ch.note_period, mod)
                        elif x == 0xC and tk == y:
                            ch.volume = 0
                        elif x == 0xD and tk == y and ch.delay_period:
                            _trigger(ch, ch.delay_period, mod)
                per = ch.period
                if e == 0 and p and per:
                    per = per * 2 ** (-(0, p >> 4, p & 0x0F)[tk % 3] / 12)
                if e in (4, 6):
                    v = VIBRATO_SINE[ch.vib_pos & 31] * ch.vib_depth / 128
                    per = per + (v if ch.vib_pos < 32 else -v)
                if ch.playing:  # un sample sans boucle s'arrête à sa fin
                    smp = mod.samples[ch.playing - 1]
                    if not smp.looped and ch.pos >= len(smp.data):
                        ch.playing = 0
                out[c].append(Tick(t, ch.playing, per, ch.volume, ch.trigger, ch.note_period))
                ch.trigger = False
                if ch.playing and per:
                    ch.pos += playback_rate(per) * dt
            tick_times.append(t)
            t += dt
        # --- ligne suivante
        if loop_to is not None:
            row = loop_to
            visited = {k for k in visited if k[0] != order}
        elif jump_order is not None:
            if jump_order >= len(mod.orders):
                break
            order, row = jump_order, (jump_row if jump_row is not None and jump_row < 64 else 0)
        else:
            row += 1
            if row >= 64:
                row, order = 0, order + 1
    return Song(nch, out, tick_times, t, rows_seen)


def _trigger(ch: _Chan, period: int, mod: Module, offset: int | None = None):
    ch.period = ch.note_period = ch.target = period
    ch.vib_pos = 0
    if ch.sample == 0:
        return
    smp = mod.samples[ch.sample - 1]
    if len(smp.data) < 4:
        ch.playing = 0  # sample vide : la voie se tait
        return
    ch.playing = ch.sample
    ch.trigger = True
    if offset is not None:
        if offset:
            ch.offset_mem = offset
        ch.pos = ch.offset_mem * 256.0
    else:
        ch.pos = 0.0


def _porta(ch: _Chan):
    if not ch.target or not ch.period:
        return
    if ch.period < ch.target:
        ch.period = min(ch.target, ch.period + ch.porta_speed)
    elif ch.period > ch.target:
        ch.period = max(ch.target, ch.period - ch.porta_speed)
