"""Remaster « électro » d'une ou plusieurs musiques, instruments choisis automatiquement (20/11/2026).

    .venv\\Scripts\\python scripts\\style_electro.py "Jim Power - ingame_1" "Terrys Big Adventure" …

Le nom est celui du dossier out\\Retravaillées\\<musique>\\ (le fichier et le n° de morceau sont retrouvés). Pour chaque
sample, d'après son son et ses notes :
- **batterie** (rôle deviné par remaster/roles.py) : grosse caisse (son grave), caisse claire, charleston fermé ou
  ouvert, cymbale (son aigu, court ou long) ; joués par le kit « 808/909 » de GeneralUser GS ;
- **basse** : un preset de basse de Surge XT ;
- les autres : **nappe** (notes longues), **arpège / pluck** (notes courtes), sinon **lead** ; un preset Surge XT
  de chaque famille, différent d'une musique à l'autre.
Le jeu reste exact (pas d'humanisation : en électro, c'est la norme). Résultat :
out\\Retravaillées\\<musique>\\<musique> (remaster électro).mp3, avec l'original à côté.

Claude ne peut pas écouter : ce sont des choix par rôle et par registre, à juger à l'oreille (puis extraits si
besoin, scripts/extraits.py).
"""
from __future__ import annotations
import json
import pathlib
import shutil
import sys
import zlib
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from remaster import render, roles, vst, paths, modfile  # noqa: E402
from remaster.__main__ import open_music  # noqa: E402

PRESETS = {
    "basse": ["Basses/Bass 1", "Basses/Sub Square", "Basses/FM Bass 1", "Basses/Rubber Bass", "Basses/Square Bass",
              "Basses/Digibass", "Basses/Bass 3", "Basses/Wide Bassline"],
    "lead": ["Leads/Classic Lead 1", "Leads/Square", "Leads/Sync Lead", "Leads/Saw Octaves", "Leads/Crisp PWM",
             "Leads/Moogy Saw", "Leads/Classic Lead 2", "Leads/Sine Lead"],
    "nappe": ["Pads/Pad 1", "Pads/MKS-70 Warm Pad", "Pads/Pad 3", "Pads/Sawteeth", "Pads/Pad 5", "Pads/Bright"],
    "arpège": ["Plucks/Nice Pluck 1", "Plucks/Saw Pluck", "Plucks/Square Pop", "Plucks/Simple PW", "Plucks/Trancy",
               "Plucks/Nice Pluck 3", "Plucks/Retrofit", "Plucks/Sync Pluck"],
}
REVERB = {"basse": 0.0, "lead": 0.18, "nappe": 0.35, "arpège": 0.25}
DRUM_KIT = 25  # « 808/909 » de GeneralUser GS
DRUMS = {"grosse caisse": (36, 0.0), "caisse claire": (38, 0.1), "charleston": (42, 0.05),
         "charleston ouvert": (46, 0.08), "cymbale": (49, 0.2), "tom": (45, 0.1)}


def find_music(name: str) -> tuple[pathlib.Path, int | None]:
    """(fichier, n° de morceau) d'une musique d'après son nom : « <Jeu> - <titre> (n) », « <Jeu> - <titre> », « <Jeu> »."""
    music = ROOT / "in" / "music"
    for game in sorted((d for d in music.iterdir() if d.is_dir()), key=lambda d: -len(d.name)):
        if name != game.name and not name.startswith(game.name + " - "):
            continue
        mod = game / f"{name}.mod"
        if mod.exists():
            return mod, None
        import import_lha
        rest = name[len(game.name) + 3:] if name != game.name else ""
        number = None
        if rest.endswith(")") and "(" in rest:
            head, _, num = rest.rpartition(" (")
            if num[:-1].isdigit():
                rest, number = head, int(num[:-1])
        for f in sorted((game / "originaux").rglob("*")):
            if f.is_file() and import_lha.uade_title(f) == rest:
                return f, number
    raise SystemExit(f"musique introuvable : {name}")


def drum_kind(sample: modfile.Sample, period: float) -> str:
    """Le genre d'un son de batterie, d'après son spectre et sa longueur joué à cette hauteur."""
    x = sample.as_float()
    sr = modfile.playback_rate(period or modfile.C2_PERIOD)
    if len(x) < 32:
        return "caisse claire"
    seg = x[: min(len(x), 16384)]
    sp = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
    fr = np.fft.rfftfreq(len(seg), 1 / sr)
    centroid = float((sp * fr).sum() / (sp.sum() or 1))
    low = float(sp[fr < 200].sum() / (sp.sum() or 1))
    length = len(x) / sr
    if low > 0.4 or centroid < 350:
        return "grosse caisse"
    if centroid > 4500 or (centroid > 3000 and roles.flatness(x) > 0.5):
        if length > 0.9 or sample.looped:
            return "cymbale"
        return "charleston ouvert" if length > 0.3 else "charleston"
    if roles.flatness(x) < 0.12 and centroid < 1500:
        return "tom"
    return "caisse claire"


def note_lengths(song, sample: int) -> list[float]:
    """Durée de chaque note d'un sample : jusqu'à la note suivante sur la même voie, ou au silence."""
    out = []
    for ticks in song.ticks:
        start = None
        for tk in ticks:
            if start is not None and (tk.trigger or tk.volume == 0 or tk.sample != sample):
                out.append(tk.time - start)
                start = None
            if tk.trigger and tk.sample == sample and tk.volume > 0:
                start = tk.time
    return out


def electro_config(m, cfg: dict, variant: int, log=print) -> dict:
    from essai_vst import make_state, BEND
    guessed = roles.guess(m.mod, m.song)
    st = roles.stats(m.mod, m.song)
    samples = {}
    for idx, role in sorted(guessed.items()):
        s = m.mod.samples[idx - 1]
        old = cfg.get("samples", {}).get(str(idx), {})
        if role == "ignoré" or old.get("mute"):
            samples[str(idx)] = {"name": "Ignoré", "mute": True}
            continue
        periods = sorted(st[idx]["periods"])
        if role == "batterie":
            kind = drum_kind(s, float(np.median(periods)) if periods else 0)
            note, rev = DRUMS[kind]
            samples[str(idx)] = {"name": kind.capitalize(), "drum": note, "drum_kit": DRUM_KIT, "reverb": rev,
                                 "velocity": 110, "comment": f"électro : {kind}, kit 808/909"}
            log(f"  sample {idx:2d} : batterie → {kind}")
            continue
        if role == "basse":
            kind = "basse"
        else:
            lens = note_lengths(m.song, idx)
            mean = float(np.median(lens)) if lens else 0.3
            kind = "nappe" if mean > 0.6 else "arpège" if mean < 0.18 else "lead"
        choices = PRESETS[kind]
        preset = choices[(variant + idx) % len(choices)]
        raw, pname = make_state("Surge XT", preset)
        rel = f"vst/{m.name}/s{idx:02d}.bin"
        vst.state_path(rel).parent.mkdir(parents=True, exist_ok=True)
        vst.state_path(rel).write_bytes(raw)
        spec = {"plugin": "Surge XT", "state": rel, "bend_range": BEND, "preset": preset}
        octave = vst.octave_offset(spec)  # preset réglé une octave plus bas ou plus haut : on compense
        samples[str(idx)] = {"name": kind.capitalize(), "reverb": REVERB[kind], "velocity": 100, "vsti": spec,
                             "comment": f"électro : {kind}, Surge XT « {pname} »"}
        if octave:  # dans le réglage du VST, pas du sample : la partition et le piano gardent les vraies notes
            spec["transpose"] = -octave
        log(f"  sample {idx:2d} : {kind} → Surge XT « {pname} »{f' (transposé de {-octave:+d})' if octave else ''}")
    out = {k: v for k, v in cfg.items() if k not in ("samples", "master", "extras")}
    out["samples"] = samples
    out["comment"] = "remaster électro (scripts/style_electro.py) : instruments choisis par Claude, sans écoute"
    out["master"] = {"loudness": -12, "pan_width": 0.35, "balance": "original", "comp_threshold": -18,
                     "fx": [{"type": "HighShelfFilter", "cutoff_frequency_hz": 9000, "gain_db": 1}],
                     "reverb": {"plugin": "DragonflyRoomReverb", "tail_s": 3, "params": {
                         "dry_level": 0, "early_level": 20, "early_send": 20, "late_level": 60, "size_m": 24,
                         "decay_s": 1.6, "predelay_ms": 20, "high_cut_hz": 9000, "late_damp_hz": 6000,
                         "low_cut_hz": 200, "low_boost": 0}}}
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for variant, name in enumerate(sys.argv[1:]):
        path, number = find_music(name)
        print(f"\n=== {name} ({path.name}{f', morceau {number}' if number else ''})", flush=True)
        m = open_music(path, number, log=lambda *a: None)
        if m.name != name:
            raise SystemExit(f"nom inattendu : {m.name} au lieu de {name}")
        cfg = render.load_config(m.cfg_path)
        backup = m.cfg_path.with_name(f"{name} (avant électro).json")
        if not backup.exists() and "électro" not in cfg.get("comment", ""):
            shutil.copy2(m.cfg_path, backup)
        seed = zlib.crc32(name.encode()) % 7
        cfg = electro_config(m, cfg, variant + seed)
        m.cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        made = render.remaster(path, cfg, m.out_dir, original=False, source=m.source, name=m.name,
                               log=lambda *a: None)
        for mp3 in made:
            dest = mp3.with_name(f"{name} (remaster électro).mp3")
            mp3.replace(dest)
            print(f"→ {dest}", flush=True)
        if m.source is not None:
            m.source[2].unlink(missing_ok=True)
        paths.copy_original(m.out_dir)


if __name__ == "__main__":
    main()
