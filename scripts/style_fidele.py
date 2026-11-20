"""Remaster « fidèle à l'esprit des instruments » (21/11/2026) : chaque sample est remplacé par le son moderne qui
lui ressemble le plus, sans changer de genre (un piano reste un piano, une basse synthé une basse synthé).

    .venv\\Scripts\\python scripts\\style_fidele.py "Jim Power - ingame_1" "Terrys Big Adventure" …

Sans oreilles, la ressemblance est mesurée note pour note :
- le sample d'origine est joué sur sa note (avec sa boucle, comme l'Amiga) ; chacun des 112 instruments General MIDI
  de GeneralUser GS (sans les bruitages) est joué sur la même note ;
- on compare le **timbre** (spectre moyen en 24 bandes, en dB, sous la fréquence la plus haute que l'Amiga pouvait
  rendre) et l'**enveloppe** (attaque, déclin, tenue : 12 points sur la durée habituelle des notes du sample) ;
- **batterie** : le kit GM le plus proche pour toute la musique (Standard, Room, Power, Electronic, 808/909, Dance),
  puis, pour chaque son, la pièce de ce kit la plus proche.
Fiche à part : songs\\<musique> (fidèle).json (la fiche électro reste). Rendu dans out\\Retravaillées\\<musique>\\fidèle\\,
le MP3 posé dans le dossier de la musique : <musique> (remaster fidèle).mp3. Les versions électro ne sont pas touchées.
"""
from __future__ import annotations
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import mido
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from remaster import render, roles, modfile, midi, analyze  # noqa: E402
from remaster.__main__ import open_music  # noqa: E402
from style_electro import find_music, note_lengths, drum_kind  # noqa: E402

SR = 22050
SF = "GeneralUser-GS.sf2"
GM_PROGRAMS = range(112)  # 112-127 : percussions et bruitages
# garde-fous de genre (le son le plus proche est choisi *dans* le genre du sample, sinon une grosse caisse devient un
# tom et une basse une nappe de cordes) : basses GM 32-39 pour la basse ; le reste sans basses ni effets (96-103)
BASS_PROGRAMS = list(range(32, 40))
OTHER_PROGRAMS = [p for p in range(112) if not 32 <= p < 40 and not 96 <= p < 104]
DRUM_FAMILY = {"grosse caisse": [35, 36], "caisse claire": [37, 38, 39, 40], "charleston": [42, 44],
               "charleston ouvert": [46, 42], "cymbale": [49, 51, 52, 55, 57, 59], "tom": [41, 43, 45, 47, 48, 50]}
KITS = {0: "Standard", 8: "Room", 16: "Power", 24: "Electronic", 25: "808/909", 26: "Dance"}
DRUM_NOTES = range(35, 82)
SLOT = 1.5  # secondes par note dans les rendus de comparaison
GM_NAMES = ["piano", "piano brillant", "piano électrique", "piano bastringue", "piano électrique 1",
            "piano électrique 2", "clavecin", "clavinet"]


def amiga_sound(s: modfile.Sample, seconds: float) -> tuple[np.ndarray, float]:
    """Le sample tel que l'Amiga le joue au C-2 (boucle comprise), à SR ; et sa fréquence d'échantillonnage d'origine."""
    x = s.as_float()
    if s.looped:
        a, n = s.loop_start, s.loop_length
        body, loop = x[:a + n], x[a:a + n]
        need = int(seconds * modfile.playback_rate(modfile.C2_PERIOD)) - len(body)
        if need > 0 and len(loop):
            x = np.concatenate([body, np.tile(loop, need // len(loop) + 1)])
    rate = modfile.playback_rate(modfile.C2_PERIOD)
    y = resample_poly(x, SR, int(round(rate))).astype(np.float32)
    return y[:int(seconds * SR)], rate


def features(x: np.ndarray, seconds: float, fmax: float) -> np.ndarray:
    """Timbre (24 bandes en dB, centrées) + enveloppe (12 points en dB, par rapport au maximum)."""
    x = x[:int(seconds * SR)]
    if len(x) < 512 or np.abs(x).max() < 1e-5:
        return np.full(36, np.nan)
    sp = np.abs(np.fft.rfft(x * np.hanning(len(x)), 1 << 15)) ** 2
    fr = np.fft.rfftfreq(1 << 15, 1 / SR)
    edges = np.geomspace(60, max(400.0, min(fmax, 9000)), 25)
    bands = np.array([sp[(fr >= lo) & (fr < hi)].sum() + 1e-12 for lo, hi in zip(edges[:-1], edges[1:])])
    timbre = 10 * np.log10(bands)
    timbre -= timbre.mean()
    frames = np.array_split(x, 12)
    env = 20 * np.log10(np.array([np.sqrt(np.mean(f ** 2)) + 1e-6 for f in frames]))
    env -= env.max()
    return np.concatenate([np.clip(timbre, -40, 40), np.clip(env, -40, 0)])


def distance(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.nanmean(np.abs(a[:24] - b[:24])) + 0.7 * np.nanmean(np.abs(a[24:] - b[24:])))


def render_series(items: list[tuple[int, int, int]], drums: bool) -> list[np.ndarray]:
    """Joue une suite de notes (programme, banque, note), une toutes les SLOT s, avec FluidSynth ; un son par note."""
    tr = mido.MidiTrack()
    ch = 9 if drums else 0
    now = 0
    tick = lambda s: int(round(s * midi.TICKS_PER_BEAT * 1e6 / midi.TEMPO))  # noqa: E731
    for k, (prog, bank, note) in enumerate(items):
        t = tick(k * SLOT)
        tr.append(mido.Message("control_change", channel=ch, control=0, value=bank, time=t - now))
        tr.append(mido.Message("program_change", channel=ch, program=prog, time=0))
        tr.append(mido.Message("note_on", channel=ch, note=note, velocity=100, time=0))
        now = t
        t2 = tick(k * SLOT + SLOT * 0.8)
        tr.append(mido.Message("note_off", channel=ch, note=note, velocity=0, time=t2 - now))
        now = t2
    with tempfile.TemporaryDirectory() as tmp:
        mid, wav = pathlib.Path(tmp) / "c.mid", pathlib.Path(tmp) / "c.wav"
        midi.midi_file([tr]).save(mid)
        render.render_stem(mid, wav, render.soundfont(SF))
        a, sr = sf.read(wav, dtype="float32", always_2d=True)
    x = resample_poly(a.mean(axis=1), SR, sr).astype(np.float32)
    return [x[int(k * SLOT * SR):int((k + 1) * SLOT * SR)] for k in range(len(items))]


def closest_gm(s: modfile.Sample, root: float, seconds: float, programs) -> tuple[int, float]:
    orig, rate = amiga_sound(s, seconds)
    note = int(min(96, max(24, round(root))))
    fmax = rate / 2 * 2 ** ((note - root) / 12)
    f0 = features(orig, seconds, fmax)
    programs = list(programs)
    sounds = render_series([(p, 0, note) for p in programs], drums=False)
    d = [distance(f0, features(x, seconds, fmax)) for x in sounds]
    best = int(np.nanargmin(d))
    return programs[best], float(d[best])


def closest_kit(drum_samples: dict[int, tuple[modfile.Sample, float]]) -> tuple[int, dict[int, int]]:
    """(kit, {sample: note GM}) : le kit qui ressemble le plus à l'ensemble des sons, puis la pièce de chacun."""
    origs = {}
    for idx, (s, period) in drum_samples.items():
        x = s.as_float()
        rate = modfile.playback_rate(period or modfile.C2_PERIOD)
        y = resample_poly(x, SR, int(round(rate))).astype(np.float32)
        origs[idx] = (features(y, 0.4, rate / 2), DRUM_FAMILY[drum_kind(s, period)])
    best = None
    for kit in KITS:
        sounds = render_series([(kit, 0, n) for n in DRUM_NOTES], drums=True)  # canal 10 : banque de batterie
        feats = [features(x, 0.4, 11000) for x in sounds]
        pick, total = {}, 0.0
        for idx, (f0, family) in origs.items():
            d = {n: distance(f0, feats[list(DRUM_NOTES).index(n)]) for n in family}
            n = min(d, key=lambda k: np.inf if np.isnan(d[k]) else d[k])
            pick[idx] = n
            total += d[n]
        if best is None or total < best[0]:
            best = (total, kit, pick)
    return best[1], best[2]


def fidele_config(m, base: dict, log=print) -> dict:
    guessed = roles.guess(m.mod, m.song)
    st = roles.stats(m.mod, m.song)
    samples, drums = {}, {}
    for idx, role in sorted(guessed.items()):
        if role == "ignoré":
            samples[str(idx)] = {"name": "Ignoré", "mute": True}
        elif role == "batterie":
            drums[idx] = (m.mod.samples[idx - 1], float(np.median(sorted(st[idx]["periods"]))))
    if drums:
        kit, pick = closest_kit(drums)
        for idx, note in pick.items():
            samples[str(idx)] = {"name": "Batterie", "drum": note, "drum_kit": kit, "reverb": 0.08, "velocity": 110,
                                 "comment": f"fidèle : kit GM {KITS[kit]}, note {note} (la plus proche du son)"}
            log(f"  sample {idx:2d} : batterie → kit {KITS[kit]}, note {note}")
    for idx, role in sorted(guessed.items()):
        if role in ("ignoré", "batterie"):
            continue
        s = m.mod.samples[idx - 1]
        inst = render.instrument({**base, "samples": {}}, m.mod, idx)
        if inst.root is None:
            continue
        lens = note_lengths(m.song, idx)
        seconds = float(min(1.0, max(0.25, np.median(lens) if lens else 0.5)))
        prog, d = closest_gm(s, inst.root, seconds, BASS_PROGRAMS if role == "basse" else OTHER_PROGRAMS)
        samples[str(idx)] = {"name": role.capitalize(), "program": prog, "velocity": 100,
                             "reverb": 0.0 if role == "basse" else 0.15,
                             "comment": f"fidèle : instrument GM {prog} (le plus proche du sample : écart {d:.1f})"}
        log(f"  sample {idx:2d} : {role} → GM {prog} (écart {d:.1f})")
    out = {k: v for k, v in base.items() if k not in ("samples", "master", "extras", "comment")}
    out["samples"] = samples
    out["comment"] = ("remaster fidèle à l'esprit des instruments (scripts/style_fidele.py) : le son GM le plus proche "
                      "de chaque sample, mesuré (timbre, enveloppe) ; choisi sans écoute")
    out["master"] = {"loudness": -14, "balance": "original"}
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for name in sys.argv[1:]:
        path, number = find_music(name)
        print(f"\n=== {name}", flush=True)
        m = open_music(path, number, log=lambda *a: None)
        base = render.load_config(m.cfg_path)
        cfg = fidele_config(m, base)
        cfg_path = m.cfg_path.with_name(f"{name} (fidèle).json")
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        work = m.out_dir / "fidèle"
        made = render.remaster(path, cfg, work, original=False, source=m.source, name=m.name, log=lambda *a: None)
        shutil.rmtree(work / "samples", ignore_errors=True)
        for mp3 in made:
            dest = m.out_dir / mp3.name
            shutil.move(str(mp3), str(dest))
            print(f"→ {dest}", flush=True)
        for f in work.glob("*(original).mp3"):
            f.unlink()  # déjà dans le dossier de la musique
        if m.source is not None:
            m.source[2].unlink(missing_ok=True)


if __name__ == "__main__":
    main()
