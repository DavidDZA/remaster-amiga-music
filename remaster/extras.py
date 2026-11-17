"""Version enrichie : de la batterie qui n'est pas dans le module (charleston, crashs).

Avec 4 voies, les musiciens Amiga gardaient souvent juste grosse caisse et caisse claire. On repère les lignes où la
batterie joue, et on ajoute :
- un charleston régulier (toutes les `every_rows` lignes), accentué sur les temps ;
- une crash au début de chaque nouvelle partie (changement de pattern) et au retour de la batterie après une pause.
"""
from __future__ import annotations
import bisect
import mido
from .modfile import Module
from .player import Song
from .midi import Instrument


def drum_rows(song: Song, drum_samples: set[int]) -> set[int]:
    """Indices (dans song.rows) des lignes où un sample de batterie démarre."""
    times = [r[2] for r in song.rows]
    rows = set()
    for c in range(song.channels):
        for tk in song.ticks[c]:
            if tk.trigger and tk.sample in drum_samples:
                rows.add(max(0, bisect.bisect_right(times, tk.time + 1e-9) - 1))
    return rows


def _active_patterns(song: Song, drows: set[int]) -> set[int]:
    """Positions de l'ordre (une par passage dans un pattern) où la batterie joue."""
    return {song.rows[i][0] for i in drows}


def crash_rows(song: Song, mod: Module, drows: set[int]) -> list[int]:
    """Lignes (indices dans song.rows) qui reçoivent une crash : début d'une nouvelle partie, retour de la batterie."""
    active = _active_patterns(song, drows)
    out = []
    for i, (order, row, _t) in enumerate(song.rows):
        if row != 0 or order not in active:
            continue
        back_after_break = order == 0 or (order - 1) not in active
        new_part = order > 0 and mod.orders[order] != mod.orders[order - 1]
        if back_after_break or new_part:
            out.append(i)
    return out


def hihat_events(song: Song, mod: Module, drows: set[int], cfg: dict) -> list:
    note = cfg.get("note", 42)
    every = cfg.get("every_rows", 2)
    accent, soft = cfg.get("velocity", [95, 70])
    beat = cfg.get("beat_rows", 4)
    active = _active_patterns(song, drows)
    skip = set(crash_rows(song, mod, drows)) if cfg.get("skip_on_crash", True) else set()
    ev = []
    for i, (order, row, t) in enumerate(song.rows):
        if order in active and row % every == 0 and i not in skip:
            vel = accent if row % beat == 0 else soft
            ev.append((t, mido.Message("note_on", channel=9, note=note, velocity=vel)))
            ev.append((t + 0.05, mido.Message("note_off", channel=9, note=note, velocity=0)))
    return ev


def crash_events(song: Song, mod: Module, drows: set[int], cfg: dict) -> list:
    note = cfg.get("note", 49)
    vel = cfg.get("velocity", 110)
    ev = []
    for i in crash_rows(song, mod, drows):
        t = song.rows[i][2]
        ev.append((t, mido.Message("note_on", channel=9, note=note, velocity=vel)))
        ev.append((t + 1.5, mido.Message("note_off", channel=9, note=note, velocity=0)))
    return ev


def extra_parts(song: Song, mod: Module, drum_samples: set[int], extras: dict) -> list[tuple[str, Instrument, list]]:
    drows = drum_rows(song, drum_samples)
    parts = []
    if "hihat" in extras:
        c = extras["hihat"]
        inst = Instrument(name="Charleston (ajouté)", drum=c.get("note", 42), drum_kit=c.get("drum_kit", 0),
                          gain_db=c.get("gain_db", -6), pan=c.get("pan", 0.3), reverb=c.get("reverb", 0.1),
                          sfz=c.get("sfz"), fx=c.get("fx", []))
        parts.append(("x-charleston", inst, hihat_events(song, mod, drows, c)))
    if "crash" in extras:
        c = extras["crash"]
        inst = Instrument(name="Crash (ajoutée)", drum=c.get("note", 49), drum_kit=c.get("drum_kit", 0),
                          gain_db=c.get("gain_db", -6), pan=c.get("pan", -0.35), reverb=c.get("reverb", 0.25),
                          sfz=c.get("sfz"), fx=c.get("fx", []))
        parts.append(("x-crash", inst, crash_events(song, mod, drows, c)))
    return parts
