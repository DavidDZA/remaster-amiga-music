"""Rendu : pistes MIDI -> FluidSynth (un fichier par piste) -> mixage -> MP3."""
from __future__ import annotations
import dataclasses
import hashlib
import json
import pathlib
import subprocess
import numpy as np
import soundfile as sf
import pedalboard as pb
import imageio_ffmpeg
from . import modfile, player, midi, analyze, extras, reference, sfz, library, fx, paths, vst

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
SR = 48000  # fréquence des amplis NAM
AMIGA_PAN = {0: -1, 1: 1, 2: 1, 3: -1}  # voies 1 et 4 à gauche, 2 et 3 à droite


def fluidsynth_exe() -> pathlib.Path:
    exe = next(TOOLS.glob("fluidsynth/*/bin/fluidsynth.exe"), None)
    if not exe:
        raise SystemExit("FluidSynth absent : lancer  .venv\\Scripts\\python scripts\\setup_tools.py")
    return exe


def openmpt_exe() -> pathlib.Path:
    return TOOLS / "openmpt" / "openmpt123" / "amd64" / "openmpt123.exe"


def soundfont(name: str) -> pathlib.Path:
    p = TOOLS / "soundfonts" / name
    if not p.exists():
        raise SystemExit(f"SoundFont absente : {p}")
    return p


def load_config(path: pathlib.Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def instrument(cfg: dict, mod: modfile.Module, sample: int, ch: int | None = None) -> midi.Instrument:
    raw = dict(cfg.get("samples", {}).get(str(sample), {}))
    raw.pop("comment", None)
    if ch is not None:
        raw.update(raw.get("by_channel", {}).get(str(ch + 1), {}))
    inst = midi.Instrument(**raw)
    if inst.root is None and inst.drum is None:
        inst.root = analyze.root_midi(mod.samples[sample - 1])
    return inst


def duplicates(song: player.Song, sample: int, ch: int) -> set:
    """Instants où ce sample attaque la même note sur une voie précédente : le module double pour faire
    plus fort ou plus large ; avec de vrais instruments, ça ferait deux guitares identiques (son flou, phasé)."""
    mine = {round(tk.time, 6): tk.note_period for tk in song.ticks[ch] if tk.trigger and tk.sample == sample}
    out = set()
    for c in range(ch):
        for tk in song.ticks[c]:
            t = round(tk.time, 6)
            if tk.trigger and tk.sample == sample and mine.get(t) == tk.note_period:
                out.add(t)
    return out


def routes(song: player.Song, mod: modfile.Module, cfg: dict):
    """Les couples (sample, voie) qui jouent vraiment, avec leurs événements MIDI."""
    used = sorted({(tk.sample, c) for c in range(song.channels) for tk in song.ticks[c] if tk.trigger})
    out = []
    for sample, ch in used:
        inst = instrument(cfg, mod, sample, ch)
        if inst.mute:
            continue
        ev = midi.route_events(song, sample, ch, inst, skip=duplicates(song, sample, ch) if inst.dedupe else None)
        if not any(m.type == "note_on" for _, m in ev):
            continue
        if inst.double:
            d = inst.double
            w = d.get("width", 0.85)
            left = dataclasses.replace(inst, pan=-w, part="G", share=0.5, double=None)
            right = dataclasses.replace(inst, pan=w, part="D", share=0.5, double=None,
                                        sfz=d.get("sfz", inst.sfz), fx=d.get("fx", inst.fx))
            delay = d.get("delay_ms", 12) / 1000
            out.append((sample, ch, left, ev))
            out.append((sample, ch, right, [(t + delay, m) for t, m in ev]))
        else:
            out.append((sample, ch, inst, ev))
    return out


def render_stem(mid_path: pathlib.Path, wav_path: pathlib.Path, sf_path: pathlib.Path):
    subprocess.run([str(fluidsynth_exe()), "-ni", "-q", "-g", "0.5", "-r", str(SR), "-O", "float", "-T", "wav",
                    "-o", "synth.reverb.active=0", "-o", "synth.chorus.active=0",
                    "-o", "synth.polyphony=512", "-F", str(wav_path), str(sf_path), str(mid_path)],
                   check=True, capture_output=True)


_SFZ_CACHE: dict = {}


ENGINE_VERSION = 4  # à augmenter quand le rendu d'une piste change (invalide le cache des pistes)


def split_fx(chain):
    """(effets lourds jusqu'au dernier ampli / baffle, effets légers après) : seuls les premiers sont mis en cache."""
    chain = list(chain or [])
    last = max((i for i, f in enumerate(chain) if f.get("type") in ("nam", "cab")), default=-1)
    return chain[:last + 1], chain[last + 1:]


def _part_key(name, ev, inst: midi.Instrument, duration: float, seed: int, default_sf: str) -> str:
    h = hashlib.sha1()
    sound = dataclasses.asdict(inst)
    for k in ("name", "gain_db", "pan", "reverb", "share", "part", "fx", "by_channel", "double"):
        sound.pop(k, None)  # réglages de mixage : n'obligent pas à refaire le son
    sound["heavy_fx"] = split_fx(inst.fx)[0]
    if sound.get("vsti") is None:
        sound.pop("vsti", None)  # pas de VST : même clé qu'avant leur arrivée (le cache des pistes reste bon)
    states = [vst.state_hash(inst.vsti)] + [vst.state_hash(f) for f in sound["heavy_fx"] if f.get("type") == "vst"]
    if any(states):
        sound["vst_states"] = states  # un autre preset choisi = une piste à refaire
    h.update(json.dumps([ENGINE_VERSION, name, sound, duration, seed, default_sf, SR],
                        sort_keys=True, default=str).encode())
    for t, m in ev:
        h.update(f"{t:.6f}{m.hex()}".encode())
    return h.hexdigest()


def render_part(name: str, ev, inst: midi.Instrument, duration: float, stem_dir: pathlib.Path,
                default_sf: str, seed: int = 0) -> np.ndarray:
    """Une piste : instrument VST3, banque SFZ (lecteur maison) ou SoundFont (FluidSynth), puis sa chaîne
    d'effets. (2, n)

    Le son avant les effets légers (EQ, compresseur… placés après le dernier ampli ou baffle) est gardé dans stems/ :
    s'il n'a pas changé (mêmes notes, même instrument, mêmes amplis), il est relu tel quel.
    """
    flac, keyfile = stem_dir / f"{name}.flac", stem_dir / f"{name}.key"
    key = _part_key(name, ev, inst, duration, seed, default_sf)
    heavy, light = split_fx(inst.fx)
    saved = keyfile.read_text().split() if keyfile.exists() else []
    if flac.exists() and len(saved) == 2 and saved[0] == key:
        audio, _ = sf.read(flac, dtype="float32", always_2d=True)
        return fx.apply(audio.T.copy() * float(saved[1]), light, SR)
    if inst.vsti:
        audio = vst.render(inst.vsti, ev, duration + midi.TAIL, SR, source_bend_range=midi.BEND_RANGE)
    elif inst.sfz:
        ck = (inst.sfz["bank"], inst.sfz["program"], tuple(sorted((inst.sfz.get("cc") or {}).items())))
        if ck not in _SFZ_CACHE:
            _SFZ_CACHE[ck] = library.load_sfz(inst.sfz["bank"], inst.sfz["program"], inst.sfz.get("cc"))
        # certaines banques sont placées une octave au-dessus du son réel (basses) : on décale les touches
        offset = int(inst.sfz.get("key_offset", library.KEY_OFFSET.get(inst.sfz["bank"], 0)))
        if offset:
            ev = [(t, m.copy(note=min(127, max(0, m.note + offset))) if m.type in ("note_on", "note_off") else m)
                  for t, m in ev]
        audio = sfz.render(_SFZ_CACHE[ck], ev, duration + midi.TAIL, SR, bend_range=midi.BEND_RANGE, seed=seed,
                           choke=inst.choke)
    else:
        mid = stem_dir / f"{name}.mid"
        midi.midi_file([midi.track(ev, inst, name, duration)]).save(mid)
        wav = stem_dir / f"{name}.wav"
        render_stem(mid, wav, soundfont(inst.soundfont or default_sf))
        audio, _ = sf.read(wav, dtype="float32", always_2d=True)
        audio = audio.T.copy()
        wav.unlink()
        mid.unlink()
    audio = fx.apply(audio, heavy, SR)
    scale = max(1.0, float(np.max(np.abs(audio))) * 1.01)  # FLAC 24 bits : pas au-delà de 1,0
    sf.write(flac, (audio / scale).T, SR, subtype="PCM_24")
    keyfile.write_text(f"{key} {scale!r}")
    return fx.apply(audio, light, SR)


def pan_of(inst: midi.Instrument, ch: int, default_width: float) -> float:
    if isinstance(inst.pan, dict):
        return float(inst.pan.get(str(ch + 1), 0.0))
    if inst.pan is not None:
        return float(inst.pan)
    return AMIGA_PAN.get(ch % 4, 0) * default_width


def mix(stems: list[tuple[np.ndarray, midi.Instrument, int, float]], master: dict) -> np.ndarray:
    """stems : (audio stéréo, instrument, voie, gain d'équilibrage)."""
    n = max(a[0].shape[1] for a in stems)
    bus = np.zeros((2, n), np.float32)
    send = np.zeros((2, n), np.float32)
    width = master.get("pan_width", 0.35)
    for audio, inst, ch, balance in stems:
        x = np.zeros((2, n), np.float32)
        x[:, : audio.shape[1]] = audio
        if inst.highpass:
            x = pb.Pedalboard([pb.HighpassFilter(inst.highpass)])(x, SR)
        p = max(-1.0, min(1.0, pan_of(inst, ch, width)))
        ang = (p + 1) * np.pi / 4  # panoramique à puissance constante
        g = balance * 10 ** (inst.gain_db / 20)
        x[0] *= g * np.cos(ang) * np.sqrt(2)
        x[1] *= g * np.sin(ang) * np.sqrt(2)
        bus += x
        send += x * inst.reverb
    # réverbération commune (départ « reverb » de chaque piste) : Dragonfly (VST3) si la fiche le demande
    rev = master.get("reverb")
    if np.any(send):
        if rev:
            wet = fx.apply(send, [{"type": "vst", **rev}], SR)[:, :n]
        else:
            room = pb.Reverb(room_size=master.get("reverb_room", 0.55), damping=0.5, wet_level=1.0,
                             dry_level=0.0, width=1.0)
            wet = pb.Pedalboard([pb.HighpassFilter(200), room])(send, SR)
        bus[:, :wet.shape[1]] += wet
    chain = pb.Pedalboard([
        pb.HighpassFilter(28),
        pb.Compressor(threshold_db=master.get("comp_threshold", -16), ratio=2.0, attack_ms=20, release_ms=200),
        pb.Limiter(threshold_db=-2.0, release_ms=100),
    ])
    bus = fx.apply(bus, master.get("fx"), SR)  # égaliseur du mix, avant compression (fiche : master.fx)
    peak = np.max(np.abs(bus)) or 1.0
    out = chain(bus / peak * 0.7, SR)
    # coupe le silence final (au-delà de la queue de réverbération)
    loud = np.where(np.max(np.abs(out), axis=0) > 1e-4)[0]
    if len(loud):
        out = out[:, : min(n, loud[-1] + SR // 2)]
    return out


def to_mp3(wav: pathlib.Path, mp3: pathlib.Path, tags: dict, loudness: float = -14.0):
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    meta = []
    for k, v in tags.items():
        meta += ["-metadata", f"{k}={v}"]
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav),
                    "-af", f"loudnorm=I={loudness}:TP=-1.5:LRA=11,aresample={SR}",
                    "-c:a", "libmp3lame", "-b:a", "320k", "-id3v2_version", "3", *meta, str(mp3)], check=True)


def render_original(mod_path: pathlib.Path, out_dir: pathlib.Path, tags: dict):
    import tempfile
    # un fichier temporaire par musique : plusieurs musiques d'un même jeu peuvent être enregistrées en même temps
    with tempfile.TemporaryDirectory() as tmp:
        wav = pathlib.Path(tmp) / "original.wav"
        subprocess.run([str(openmpt_exe()), "--batch", "--quiet", "--stereo", "60", "--samplerate", str(SR),
                        "--no-float", "--force", "-o", str(wav), str(mod_path)], check=True, capture_output=True)
        to_mp3(wav, out_dir / f"{mod_path.stem} (original).mp3",
               {**tags, "title": f"{tags.get('title', mod_path.stem)} (original Amiga)"})


def export_samples(mod: modfile.Module, out_dir: pathlib.Path):
    """Les samples d'origine en WAV, pour les écouter et choisir leurs remplaçants."""
    d = out_dir / "samples"
    d.mkdir(parents=True, exist_ok=True)
    rate = int(modfile.playback_rate(modfile.C2_PERIOD))
    for s in mod.samples:
        if len(s.data) >= 4:
            safe = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in s.name).strip() or "sans nom"
            sf.write(d / f"{s.index:02d} - {safe}.wav", s.as_float(), rate, subtype="PCM_16")


def remaster(mod_path: pathlib.Path, cfg: dict, out_dir: pathlib.Path, original: bool = True, log=print,
             source=None, name: str | None = None, original_dir: pathlib.Path | None = None):
    """out_dir : le dossier de travail de la musique (out\\<Jeu>\\<musique>\\) ; le MP3 de l'original va avec les
    autres musiques du jeu (original_dir, par défaut out\\<Jeu>\\).
    source : (Module, Song, WAV d'origine) déjà prêts, pour une musique qui n'est pas un .mod (remaster/paula.py).
    name : nom des fichiers produits (par défaut celui du fichier de musique)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    original_dir = original_dir or paths.game_dir(mod_path)
    original_dir.mkdir(parents=True, exist_ok=True)
    stem = name or mod_path.stem
    if source is None:
        mod = modfile.load(mod_path)
        song = player.play(mod)
    else:
        mod, song, original_wav = source
    log(f"« {mod.title} » : {mod.channels} voies, {song.duration:.1f} s")
    rts = routes(song, mod, cfg)
    stem_dir = out_dir / "stems"
    stem_dir.mkdir(exist_ok=True)
    default_sf = cfg.get("soundfont", "GeneralUser-GS.sf2")
    stems = []
    for sample, ch, inst, ev in rts:
        name = f"s{sample:02d}-v{ch + 1}{inst.part}"
        audio = render_part(name, ev, inst, song.duration, stem_dir, default_sf,
                            seed=sample * 10 + ch + (500 if inst.part == "D" else 0))
        stems.append((audio, inst, ch, 1.0))
        log(f"  piste {name} : {inst.name or '?'}")
    if cfg.get("master", {}).get("balance", "original") == "original":
        stems = balance_on_original(stems, rts, song, mod)
    comb = midi.combined(song, [r for r in rts if r[2].part != "D"])
    if comb:
        comb.save(out_dir / f"{stem} (remaster).mid")
    master = cfg.get("master", {})
    title = cfg.get("title", mod.title if source is None and mod.title else stem)
    tags = {"title": title, "artist": cfg.get("artist", ""),
            "album": cfg.get("album", "Remaster AMIGA Music"), "comment": f"Remaster de {stem}"}
    made = [_write_mix(stems, master, out_dir, f"{stem} (remaster fidèle).mp3",
                       {**tags, "title": f"{title} (fidèle)"})]
    if cfg.get("extras"):
        drum_samples = {s for s, _, inst, _ in rts if inst.drum is not None}
        hit = per_hit_energy([(st[0], st[3], ev) for st, (_, _, inst, ev) in zip(stems, rts) if inst.drum is not None])
        extra_stems = list(stems)
        for name, inst, ev in extras.extra_parts(song, mod, drum_samples, cfg["extras"]):
            if not ev:
                continue
            a = render_part(name, ev, inst, song.duration, stem_dir, default_sf, seed=999)
            own = per_hit_energy([(a, 1.0, ev)])
            g = float(np.sqrt(hit / own)) if hit and own else 1.0  # un coup ajouté = un coup de la batterie d'origine
            extra_stems.append((a, inst, 0, g))
            log(f"  piste {name} : {inst.name}")
        made.append(_write_mix(extra_stems, master, out_dir, f"{stem} (remaster enrichi).mp3",
                               {**tags, "title": f"{title} (enrichi)"}))
    if original and source is None:
        render_original(mod_path, original_dir, tags)
    elif original:
        to_mp3(original_wav, original_dir / f"{stem} (original).mp3",
               {**tags, "title": f"{title} (original Amiga)"})
    export_samples(mod, out_dir)
    for m in made:
        log(f"→ {m}")
    return made


def per_hit_energy(parts) -> float:
    """Énergie moyenne d'un coup : parts = [(audio, gain, événements MIDI)]."""
    energy = sum(reference.weighted_energy(a.mean(axis=0), SR) * g * g for a, g, _ in parts)
    hits = sum(1 for _, _, ev in parts for _, m in ev if m.type == "note_on" and m.velocity > 0)
    return energy / hits if hits else 0.0


def balance_on_original(stems, rts, song, mod):
    """Chaque piste prend dans le mix la même part qu'avait son sample dans le module d'origine."""
    ref_sr = 22050
    e_old = [reference.weighted_energy(reference.original_stem(song, mod, s, ch, ref_sr), ref_sr) * inst.share
             for s, ch, inst, _ in rts]
    e_new = [reference.weighted_energy(a.mean(axis=0), SR) * ref_sr / SR for a, _, _, _ in stems]
    to, tn = sum(e_old) or 1.0, sum(e_new) or 1.0
    out = []
    for (a, inst, ch, _), eo, en in zip(stems, e_old, e_new):
        g = float(np.sqrt((eo / to) / (en / tn))) if en > 0 and eo > 0 else 1.0
        out.append((a, inst, ch, g))
    return out


def _write_mix(stems, master: dict, out_dir: pathlib.Path, name: str, tags: dict) -> pathlib.Path:
    wav = out_dir / "mix.wav"
    sf.write(wav, mix(stems, master).T, SR, subtype="FLOAT")
    mp3 = out_dir / name
    to_mp3(wav, mp3, tags, master.get("loudness", -14.0))
    wav.unlink()
    return mp3
