"""Des ticks du module aux notes MIDI : une piste par couple (sample, voie du module).

Chaque piste est monophonique comme une voie Amiga : les glissandos et le vibrato deviennent du pitch bend,
les changements de volume du CC 11 (expression).
"""
from __future__ import annotations
from dataclasses import dataclass, field
import math
import mido
from .modfile import period_to_semitones
from .player import Song

TICKS_PER_BEAT = 480
TEMPO = 500_000          # 120 BPM : 1 tick MIDI = 1/960 s
BEND_RANGE = 24          # demi-tons
TAIL = 3.0               # secondes laissées à la fin pour les queues de son


@dataclass
class Instrument:
    """Ce qui remplace un sample. Un `drum` (n° de note GM) ou un `program` (instrument GM)."""
    name: str = ""
    program: int | None = 0
    bank: int = 0
    drum: int | None = None
    drum_kit: int = 0            # programme du kit (canal 10) : 0 Standard, 16 Power, 25 TR-808…
    root: float | None = None    # note MIDI du sample joué au C-2 (deviné si absent)
    transpose: int = 0
    chord: list[int] = field(default_factory=lambda: [0])  # ex. [0, 7, 12] : power chord
    velocity: int = 100
    max_length: float | None = None  # coupe les notes trop longues (secondes)
    soundfont: str | None = None
    gain_db: float = 0.0
    pan: float | dict | None = None  # -1 (gauche) … 1 (droite), ou {voie: pan}
    reverb: float = 0.15
    highpass: float | None = None
    mute: bool = False


def _seconds_to_ticks(t: float) -> int:
    return int(round(t * TICKS_PER_BEAT * 1e6 / TEMPO))


def route_events(song: Song, sample: int, channel: int, inst: Instrument) -> list[tuple[float, mido.Message]]:
    """Événements (temps, message) d'un sample joué sur une voie, sur le canal MIDI 0 (ou 9 pour la batterie)."""
    midi_ch = 9 if inst.drum is not None else 0
    ev: list[tuple[float, mido.Message]] = []
    on: list[int] = []
    on_since = 0.0
    bend0 = 0.0
    last_bend = None
    last_expr = None
    root = inst.root if inst.root is not None else 60.0

    def note_off(t):
        nonlocal on
        for n in on:
            ev.append((t, mido.Message("note_off", channel=midi_ch, note=n, velocity=0)))
        on = []

    for tk in song.ticks[channel]:
        mine = tk.sample == sample
        if on and (tk.trigger or not mine):
            note_off(tk.time)
        if on and inst.max_length and tk.time - on_since >= inst.max_length:
            note_off(tk.time)
        if tk.trigger and mine:
            on_since = tk.time
            if inst.drum is not None:
                vel = max(1, min(127, round(inst.velocity * math.sqrt(tk.volume / 64))))
                if tk.volume > 0:
                    ev.append((tk.time, mido.Message("note_on", channel=midi_ch, note=inst.drum, velocity=vel)))
                    on = [inst.drum]
                continue
            semis = root + period_to_semitones(tk.note_period) + inst.transpose
            base = round(semis)
            bend0 = semis - base
            notes = [base + c for c in inst.chord if 0 <= base + c <= 127]
            last_bend = _bend(ev, tk.time, midi_ch, bend0, None)
            last_expr = _expr(ev, tk.time, midi_ch, tk.volume, None)
            for n in notes:
                ev.append((tk.time, mido.Message("note_on", channel=midi_ch, note=n, velocity=inst.velocity)))
            on = notes
            continue
        if on and mine and inst.drum is None:
            if tk.period:
                semis = 12 * math.log2(tk.note_period / tk.period) + bend0
                last_bend = _bend(ev, tk.time, midi_ch, semis, last_bend)
            last_expr = _expr(ev, tk.time, midi_ch, tk.volume, last_expr)
    if on:
        note_off(song.duration)
    return ev


def _bend(ev, t, ch, semis, last):
    v = max(-8192, min(8191, round(semis / BEND_RANGE * 8192)))
    if v != last:
        ev.append((t, mido.Message("pitchwheel", channel=ch, pitch=v)))
    return v


def _expr(ev, t, ch, volume, last):
    v = round(127 * math.sqrt(max(0, min(64, volume)) / 64))
    if v != last:
        ev.append((t, mido.Message("control_change", channel=ch, control=11, value=v)))
    return v


def track(events, inst: Instrument, name: str, duration: float) -> mido.MidiTrack:
    tr = mido.MidiTrack()
    # les noms de piste MIDI sont en latin-1 : « œ » n'y est pas
    latin = name.replace("œ", "oe").replace("Œ", "OE").encode("latin-1", "replace").decode("latin-1")
    tr.append(mido.MetaMessage("track_name", name=latin, time=0))
    if inst.drum is not None:
        tr.append(mido.Message("program_change", channel=9, program=inst.drum_kit, time=0))
    else:
        tr.append(mido.Message("control_change", channel=0, control=0, value=inst.bank, time=0))
        tr.append(mido.Message("program_change", channel=0, program=inst.program or 0, time=0))
        for cc, val in ((101, 0), (100, 0), (6, BEND_RANGE), (38, 0), (101, 127), (100, 127)):
            tr.append(mido.Message("control_change", channel=0, control=cc, value=val, time=0))
    tr.append(mido.Message("control_change", channel=9 if inst.drum is not None else 0, control=7, value=127, time=0))
    now = 0
    for t, msg in sorted(events, key=lambda e: (e[0], 0 if e[1].type == "note_off" else 1)):
        tt = _seconds_to_ticks(t)
        tr.append(msg.copy(time=tt - now))
        now = tt
    end = _seconds_to_ticks(duration + TAIL)
    tr.append(mido.MetaMessage("end_of_track", time=max(0, end - now)))
    return tr


def midi_file(tracks: list[mido.MidiTrack]) -> mido.MidiFile:
    mf = mido.MidiFile(type=1, ticks_per_beat=TICKS_PER_BEAT)
    tempo = mido.MidiTrack()
    tempo.append(mido.MetaMessage("set_tempo", tempo=TEMPO, time=0))
    mf.tracks.append(tempo)
    mf.tracks.extend(tracks)
    return mf


def combined(song: Song, routes: list[tuple[int, int, Instrument, list]]) -> mido.MidiFile | None:
    """Un seul fichier MIDI (pour un logiciel de musique) : un canal par piste, s'il y en a 15 au plus."""
    tonal = [r for r in routes if r[2].drum is None]
    if len(tonal) > 15:
        return None
    tracks = []
    free = [c for c in range(16) if c != 9]
    for (sample, ch, inst, ev) in routes:
        mch = 9 if inst.drum is not None else free.pop(0)
        evs = [(t, m.copy(channel=mch)) for t, m in ev]
        tr = track(evs, inst, f"{inst.name or 'sample ' + str(sample)} (voie {ch + 1})", song.duration)
        for m in tr:
            if not m.is_meta:
                m.channel = mch
        tracks.append(tr)
    return midi_file(tracks)
