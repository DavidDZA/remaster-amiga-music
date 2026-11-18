"""Arrangement pour piano seul : un MP3 (Salamander Grand Piano) et sa partition (PDF).

    python -m remaster.piano "in\\mod\\Dr Mario\\Dr Mario.mod"

Règles d'arrangement (fiche du morceau, clé `piano`) :
- **main droite, hampes en haut** : la mélodie, prise dans la partie de lead des tablatures (`melody`). Un bend
  tenu devient la note atteinte (le piano ne peut pas tirer une corde) ; une mélodie trop grave monte d'une octave ;
- **main droite, hampes en bas** : des accords de trois sons sous la mélodie. Les guitares jouent des quintes (sans
  tierce) : la tierce est choisie d'après la tonalité du passage et les notes de la mélodie. Pas d'accords sous une
  mélodie trop rapide (plus de 8 notes par mesure) : la main n'a pas le temps ;
- **main gauche** : là où la guitare étouffée joue (`riff`), le riff lui-même, une octave plus bas, en notes piquées,
  avec l'octave sur les accords ; ailleurs la basse en octaves, une attaque par temps quand elle répète la même note ;
- pédale changée à chaque accord, sauf dans les riffs (le son doit rester sec).

Le tempo et les durées sont ceux du module : le MP3 se cale sur l'original et sur les remasters.
"""
from __future__ import annotations
import argparse
import pathlib
import random
from dataclasses import dataclass, field
import mido
import numpy as np
import soundfile as sf
from . import score, lily, midi, fx
from .partitions import Context

DEFAULTS = {
    "melody": "Guitare 1 (lead)",
    "chords": [],          # samples qui donnent l'harmonie (power chords, chœur)
    "riff": [],            # samples du riff étouffé (main gauche piquée)
    "bass": [],            # samples de la basse
    "dense": 8,            # au-delà de tant de notes de mélodie par mesure : pas d'accords sous la mélodie
    "soundfont": "SalamanderGrandPiano-V3+20200602.sf2",
    "loudness": -16,
    "reverb": {"plugin": "DragonflyHallReverb", "tail_s": 3,
               "params": {"dry_level": 80, "early_level": 12, "late_level": 22, "size_m": 26, "decay_s": 1.9,
                          "predelay_ms": 14, "low_cut_hz": 60, "high_cut_hz": 9000, "width": 100}},
}

LEGEND = ("Arrangement pour piano seul. Main droite : la mélodie de la guitare lead (hampes en haut) et des accords "
          "(hampes en bas). Main gauche : la basse en octaves, ou le riff de guitare étouffée (notes piquées). "
          "Péd. : changer la pédale à chaque accord ; sans Péd. : jouer sec. "
          "Lettres encadrées : début d'une partie, avec le temps dans le MP3.")


@dataclass
class PNote:
    row: int
    end: int
    pitches: tuple[int, ...]
    velocity: int = 70
    staccato: bool = False


@dataclass
class Arrangement:
    melody: list[PNote] = field(default_factory=list)
    chords: list[PNote] = field(default_factory=list)
    left: list[PNote] = field(default_factory=list)
    pedal_bars: set[int] = field(default_factory=set)   # mesures jouées avec la pédale
    pedal_rows: list[int] = field(default_factory=list)  # lignes où l'on reprend la pédale
    marks: dict[int, list[str]] = field(default_factory=dict)


def settings(cfg: dict) -> dict:
    return {**DEFAULTS, **(cfg.get("piano") or {})}


# --- harmonie -----------------------------------------------------------------------------------------------------

def harmony(ctx: Context, p: dict, bar_of: list[int]) -> list[tuple[int, int]]:
    """(ligne, fondamentale 0-11) à chaque changement d'accord : power chords / chœur, sinon la basse."""
    chord_s, bass_s = set(p["chords"]), set(p["bass"])
    by_row: dict[int, list[score.Hit]] = {}
    for h in ctx.hits:
        if h.sample in chord_s:
            by_row.setdefault(h.row, []).append(h)
    bars_with_chords = {bar_of[r] for r in by_row}
    changes = {}
    for r, hs in by_row.items():
        first = [h for h in hs if h.sample == p["chords"][0]]  # le premier sample listé passe avant (guitare)
        src = first or hs
        changes[r] = min(min(h.pitches) for h in src) % 12
    for h in ctx.hits:
        if h.sample in bass_s and bar_of[h.row] not in bars_with_chords:
            changes.setdefault(h.row, h.pitches[0] % 12)
    out = []
    for r in sorted(changes):
        if not out or out[-1][1] != changes[r]:
            out.append((r, changes[r]))
    return out


def section_keys(ctx: Context) -> list[tuple[int, bool]]:
    """Tonalité de chaque mesure : celle de sa partie (repère), estimée avec la partie d'avant et d'après."""
    starts = sorted(ctx.sections) + [len(ctx.bars)]
    tonal = [h for h in ctx.hits if not score._is_drum(ctx.cfg, h.sample)]
    bar_of = score._bar_index(ctx.bars)
    keys = [ctx.key] * len(ctx.bars)
    for k in range(len(starts) - 1):
        lo, hi = starts[max(0, k - 1)], starts[min(len(starts) - 1, k + 2)]
        hs = [h for h in tonal if lo <= bar_of[h.row] < hi]
        key = score.estimate_key(score.pitch_classes(hs)) if hs else ctx.key
        for b in range(starts[k], starts[k + 1]):
            keys[b] = key
    return keys


def third_of(root: int, key: tuple[int, bool], melody_pcs: list[int]) -> int:
    """Tierce majeure ou mineure : celle que chante la mélodie, sinon celle de la gamme du passage."""
    minor, major = (root + 3) % 12, (root + 4) % 12
    sc = score.scale(key)
    s_min = 2 * melody_pcs.count(minor) + (1 if minor in sc else 0)
    s_maj = 2 * melody_pcs.count(major) + (1 if major in sc else 0)
    if s_maj > s_min:
        return major
    if s_min > s_maj:
        return minor
    return minor if minor in sc else major


def voicing(pcs: list[int], top_max: int, target_top: int, prev: tuple[int, ...] | None,
            low: int = 52) -> tuple[int, ...]:
    """Accord serré (3 sons dans l'octave) dont la note du haut ne dépasse pas top_max ; proche du précédent."""
    best, best_cost = (), None
    for top in range(low + 4, top_max + 1):
        if top % 12 not in pcs:
            continue
        notes = [top]
        for pc in pcs:
            if pc == top % 12:
                continue
            n = top - ((top - pc) % 12)
            notes.append(n)
        notes = tuple(sorted(notes))
        if notes[0] < low or notes[-1] - notes[0] > 12:
            continue
        cost = abs(top - target_top)
        if prev:
            cost = 0.6 * cost + sum(abs(a - b) for a, b in zip(notes, prev)) / len(notes)
        if best_cost is None or cost < best_cost:
            best, best_cost = notes, cost
    return best


# --- arrangement --------------------------------------------------------------------------------------------------

def arrange(ctx: Context, cfg: dict) -> Arrangement:
    p = settings(cfg)
    bar_of = score._bar_index(ctx.bars)
    nrows = len(ctx.song.rows)
    arr = Arrangement()
    parts = score.assign(ctx.hits + ctx.extras, cfg.get("partitions") or {}, ctx.bars)
    mel_events = score.events(parts.get(p["melody"], []))
    arr.melody = melody_notes(ctx, mel_events)
    mel_by_bar: dict[int, list[PNote]] = {}
    for n in arr.melody:
        mel_by_bar.setdefault(bar_of[n.row], []).append(n)

    changes = harmony(ctx, p, bar_of)
    keys = section_keys(ctx)
    riff_s, chord_s, bass_s = set(p["riff"]), set(p["chords"]), set(p["bass"])
    hits_by_bar: dict[int, list[score.Hit]] = {}
    for h in ctx.hits:
        hits_by_bar.setdefault(bar_of[h.row], []).append(h)

    def chord_at(r: int):
        k = max((i for i, (cr, _pc) in enumerate(changes) if cr <= r), default=None)
        return None if k is None else changes[k]

    prev_voicing = None
    pedal_state = None
    for b, (start, n) in enumerate(ctx.bars):
        stop = start + n
        bhits = hits_by_bar.get(b, [])
        riff = any(h.sample in riff_s for h in bhits)
        mel = mel_by_bar.get(b, [])
        dense = len(mel) > p["dense"]
        has_harmony = any(h.sample in chord_s | bass_s for h in bhits)
        # repère de pédale (texte) quand on passe du sec au lié et inversement
        want = None if not bhits else (not riff)
        if want is not None and want != pedal_state:
            arr.marks.setdefault(start, []).append("Péd." if want else "sans Péd.")
            pedal_state = want
        if want:
            arr.pedal_bars.add(b)

        # segments d'harmonie de la mesure
        cuts = sorted({start} | {r for r, _ in changes if start < r < stop})
        segments = []
        for k, r in enumerate(cuts):
            c = chord_at(r)
            if c is None or not has_harmony:
                continue
            segments.append((r, cuts[k + 1] if k + 1 < len(cuts) else stop, c[1]))
        if want:
            arr.pedal_rows += [s for s, _e, _pc in segments]

        def triad(root, s, e, top_max, target):
            nonlocal prev_voicing
            mel_pcs = [x % 12 for m in arr.melody if s <= m.row < e or (m.row < s < m.end) for x in m.pitches]
            pcs = [root, third_of(root, keys[b], mel_pcs), (root + 7) % 12]
            v = voicing(pcs, top_max, target, prev_voicing)
            if v:
                prev_voicing = v
            return v

        def top_limit(s, e):
            ms = [min(m.pitches) for m in arr.melody if m.row < e and m.end > s]  # tenues comprises
            return (min(ms) - 1, min(min(ms) - 3, 72)) if ms else (76, 72)

        # main droite, accords
        if not dense:
            if riff:
                stabs = sorted({h.row for h in bhits if h.sample in chord_s})
                for k, r in enumerate(stabs):
                    hs = [h for h in bhits if h.row == r and h.sample in chord_s]
                    longest = max(h.end for h in hs)
                    e = min(longest, stabs[k + 1] if k + 1 < len(stabs) else stop, stop)
                    if longest - r <= 8:
                        e = min(e, r + 4)  # accord bref dans le module : une attaque, pas une nappe
                    c = chord_at(r)
                    tmax, target = top_limit(r, e)
                    v = triad(c[1], r, e, tmax, target) if c else ()
                    if v:
                        arr.chords.append(PNote(r, e, v, 60))
            else:
                for s, e, root in segments:
                    tmax, target = top_limit(s, e)
                    v = triad(root, s, e, tmax, target)
                    if v:
                        arr.chords.append(PNote(s, e, v, 54))

        # main gauche
        if riff:
            onsets: dict[int, list[score.Hit]] = {}
            for h in bhits:
                if h.sample in riff_s or h.sample in chord_s:
                    onsets.setdefault(h.row, []).append(h)
            rows = sorted(onsets)
            for k, r in enumerate(rows):
                hs = onsets[r]
                low = min(min(h.pitches) for h in hs)
                low = 36 + (low - 36) % 12
                stab = any(h.sample in chord_s for h in hs)
                nxt = rows[k + 1] if k + 1 < len(rows) else stop
                if stab:
                    arr.left.append(PNote(r, min(nxt, r + 8, stop), (low, low + 12), 76))
                else:
                    arr.left.append(PNote(r, min(nxt, r + 2, stop), (low,), 64, staccato=True))
        elif any(h.sample in bass_s for h in bhits):
            bh = sorted((h for h in bhits if h.sample in bass_s), key=lambda h: h.row)
            kept = []
            for h in bh:
                pc_low = 31 + (h.pitches[0] - 31) % 12
                if kept and kept[-1][1] == pc_low and (h.row - start) % score.ROWS_PER_BEAT:
                    continue  # même note répétée dans le temps : une attaque par temps suffit
                kept.append((h.row, pc_low))
            for k, (r, low) in enumerate(kept):
                nxt = kept[k + 1][0] if k + 1 < len(kept) else stop
                arr.left.append(PNote(r, min(nxt, stop), (low, low + 12), 66))
        else:
            for s, e, root in segments:
                low = 31 + (root - 31) % 12
                arr.left.append(PNote(s, e, (low, low + 12), 62))
    arr.chords = [c for c in arr.chords if c.end > c.row]
    for lst in (arr.chords, arr.left):
        for nt in lst:
            nt.end = min(nt.end, nrows)
    return arr


def melody_notes(ctx: Context, evs: list[score.Event]) -> list[PNote]:
    """La mélodie : bends tenus remplacés par la note atteinte, octave remontée si le passage est trop grave."""
    out = []
    for e in evs:
        top = max(e.pitches)
        bend = [round(x) for x in e.bend] or [0]
        r, cur = e.row, bend[0]
        for k in range(1, e.end - e.row + 1):
            val = bend[k] if k < len(bend) else bend[-1]
            end_here = k == e.end - e.row
            # nouvelle note si la hauteur atteinte change et tient au moins deux lignes
            held = all((bend[j] if j < len(bend) else bend[-1]) == val for j in range(k, min(k + 2, e.end - e.row)))
            if end_here or (val != cur and held and abs(val) <= 3):
                out.append(PNote(r, e.row + k, (top + cur,), 82))
                r, cur = e.row + k, val
    # octave : par partie (repère), une mélodie trop grave monte
    bar_of = score._bar_index(ctx.bars)
    starts = sorted(ctx.sections) + [len(ctx.bars)]
    for k in range(len(starts) - 1):
        notes = [n for n in out if starts[k] <= bar_of[n.row] < starts[k + 1]]
        if notes and sum(n.pitches[0] for n in notes) / len(notes) < 64:
            for n in notes:
                n.pitches = (n.pitches[0] + 12,)
    for n in out:  # une note isolée trop grave pour la main droite (sous sol 3) : une octave plus haut
        if n.pitches[0] < 55:
            n.pitches = (n.pitches[0] + 12,)
    return [n for n in out if n.end > n.row]


# --- son ----------------------------------------------------------------------------------------------------------

def to_midi(ctx: Context, arr: Arrangement, seed: int = 7) -> list[tuple[float, mido.Message]]:
    t = score.row_seconds(ctx.song)
    rnd = random.Random(seed)
    ev = []

    def add(notes: list[PNote], accent_beats: bool):
        for nt in notes:
            on = t[nt.row] + rnd.uniform(-0.006, 0.006)
            off = t[nt.end] - 0.012
            if nt.staccato:
                off = min(off, on + 0.09)
            vel = nt.velocity + rnd.randint(-3, 3)
            if accent_beats and nt.row % score.ROWS_PER_BEAT == 0:
                vel += 6
            for pch in nt.pitches:
                ev.append((max(0.0, on), mido.Message("note_on", channel=0, note=pch, velocity=max(1, min(127, vel)))))
                ev.append((max(on + 0.03, off), mido.Message("note_off", channel=0, note=pch, velocity=0)))
    add(arr.melody, True)
    add(arr.chords, False)
    add(arr.left, True)
    # pédale : relevée juste au changement d'accord, reprise un peu après
    bar_of = score._bar_index(ctx.bars)
    rows = sorted(set(arr.pedal_rows))
    down = False
    for k, r in enumerate(rows):
        if down:
            ev.append((t[r] - 0.01, mido.Message("control_change", channel=0, control=64, value=0)))
        ev.append((t[r] + 0.05, mido.Message("control_change", channel=0, control=64, value=127)))
        down = True
        nxt = rows[k + 1] if k + 1 < len(rows) else None
        # lever la pédale si la mesure suivante est jouée sèche
        b = bar_of[r]
        if nxt is None or bar_of[nxt] > b + 1 or (b + 1 < len(ctx.bars) and b + 1 not in arr.pedal_bars):
            s, n = ctx.bars[b]
            end = t[min(s + n, len(t) - 1)]
            ev.append((end - 0.01, mido.Message("control_change", channel=0, control=64, value=0)))
            down = False
    return ev


def soundfont_path(name: str) -> pathlib.Path:
    found = list(lily.TOOLS.joinpath("piano").rglob(name)) or list(lily.TOOLS.joinpath("soundfonts").rglob(name))
    if not found:
        raise SystemExit(f"Piano absent : {name} (lancer  .venv\\Scripts\\python scripts\\setup_tools.py)")
    return found[0]


def render_mp3(ctx: Context, arr: Arrangement, p: dict, out_dir: pathlib.Path, mod_stem: str) -> pathlib.Path:
    from . import render
    ev = to_midi(ctx, arr)
    inst = midi.Instrument(name="Piano", program=0)
    mid = out_dir / f"{mod_stem} (piano).mid"
    midi.midi_file([midi.track(ev, inst, "Piano", ctx.song.duration)]).save(mid)
    wav = out_dir / "piano.wav"
    render.render_stem(mid, wav, soundfont_path(p["soundfont"]))
    audio, sr = sf.read(wav, dtype="float32", always_2d=True)
    wav.unlink()
    x = audio.T.copy()
    if p.get("reverb"):
        x = fx.apply(x, [{"type": "vst", **p["reverb"]}], sr)
    loud = np.where(np.max(np.abs(x), axis=0) > 1e-4)[0]
    if len(loud):
        x = x[:, : loud[-1] + sr // 2]
    x = x / (np.max(np.abs(x)) or 1.0) * 0.8
    mix = out_dir / "piano-mix.wav"
    sf.write(mix, x.T, sr, subtype="FLOAT")
    mp3 = out_dir / f"{mod_stem} (piano).mp3"
    title = ctx.cfg.get("title", mod_stem).replace(" (remaster)", "")
    render.to_mp3(mix, mp3, {"title": f"{title} (piano)", "artist": ctx.cfg.get("artist", ""),
                             "album": "Remaster AMIGA Music", "comment": "Piano : Salamander Grand Piano (CC-BY)"},
                  p.get("loudness", -16))
    mix.unlink()
    return mp3


# --- partition ----------------------------------------------------------------------------------------------------

def score_ly(ctx: Context, arr: Arrangement) -> str:
    def voice(notes: list[PNote], empty: str, tie_ok: bool = True) -> str:
        evs = [score.Event(n.row, n.end, n.pitches) for n in notes]
        style = {id(e): n for e, n in zip(evs, notes)}
        per_bar = ctx.split_bars(evs)
        out = []
        for b, (_s, n) in enumerate(ctx.bars):
            items = []
            for pos, ln, e, first, tie in per_bar.get(b, []):
                nt = style[id(e)]
                names = [lily.pitch(x, ctx.flats) for x in nt.pitches]
                body = names[0] if len(names) == 1 else "<" + " ".join(names) + ">"
                extra = "-." if (nt.staccato and first) else ""
                if nt.staccato:  # note piquée : jamais liée, le reste de la durée est un silence
                    if not first:
                        continue
                    ln, tie = lily.split(pos, ln, n)[0], False
                items.append((pos, ln, body, extra, tie and tie_ok))
            out.append(lily.bar_music(n, items, empty))
        return out

    mel = voice(arr.melody, "s")
    acc = voice(arr.chords, "s")
    left = voice(arr.left, "R")
    # mesure muette pour toute la main droite : une pause dans la voix du haut
    for b in range(len(ctx.bars)):
        if mel[b].startswith("s") and acc[b].startswith("s"):
            mel[b] = mel[b].replace("s", "R", 1)
    return f"""melody = {{
  \\compressEmptyMeasures
  {ctx.join_bars(mel)}
}}
accomp = {{
  {ctx.join_bars(acc)}
}}
left = {{
  {ctx.join_bars(left)}
}}
marks = {{
  {ctx.marks_voice(arr.marks)}
}}
\\score {{
  \\new PianoStaff \\with {{ instrumentName = "Piano" }} <<
    \\new Staff = "md" <<
      \\new Voice = "mel" {{ \\voiceOne \\clef treble {ctx.key_command()} \\melody }}
      \\new Voice = "acc" {{ \\voiceTwo \\accomp }}
      \\new Voice {{ \\marks }}
    >>
    \\new Staff = "mg" {{ \\clef bass {ctx.key_command()} \\left }}
  >>
  \\layout {{ indent = 12 }}
}}
"""


def make(mod_path: pathlib.Path, cfg: dict, out_dir: pathlib.Path, log=print, audio: bool = True):
    p = settings(cfg)
    ctx = Context(mod_path, cfg)
    out_dir.mkdir(parents=True, exist_ok=True)
    arr = arrange(ctx, cfg)
    log(f"  piano : mélodie {len(arr.melody)} notes, accords {len(arr.chords)}, main gauche {len(arr.left)}")
    sheet_dir = out_dir / "partitions"
    sheet_dir.mkdir(exist_ok=True)
    ly = sheet_dir / f"{ctx.title} - Piano.ly"
    ly.write_text(lily.header(ctx.title, "Piano (arrangement)", ctx.composer, LEGEND) + score_ly(ctx, arr),
                  encoding="utf-8")
    made = [lily.compile_pdf(ly)]
    if audio:
        made.append(render_mp3(ctx, arr, p, out_dir, mod_path.stem))
    for m in made:
        log(f"→ {m}")
    return made


def main():
    import sys
    from .render import load_config, ROOT
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Arrangement pour piano seul d'un module Amiga : MP3 et partition.")
    ap.add_argument("mod", type=pathlib.Path)
    ap.add_argument("--config", type=pathlib.Path)
    ap.add_argument("--out", type=pathlib.Path)
    ap.add_argument("--sans-mp3", action="store_true", help="seulement la partition")
    a = ap.parse_args()
    cfg = load_config(a.config or ROOT / "songs" / f"{a.mod.stem}.json")
    make(a.mod, cfg, a.out or ROOT / "out" / a.mod.stem, audio=not a.sans_mp3)


if __name__ == "__main__":
    main()
