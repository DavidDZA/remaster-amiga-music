"""Un essai de remaster avec des presets VST choisis d'avance (sans fenêtre), à côté du remaster existant.

    .venv\\Scripts\\python scripts\\essai_vst.py "in\\music\\Dr Mario\\Dr Mario.mod" "essai VST 1" \\
        5="Surge XT:Leads/Synth Guitar 1" 10="Surge XT:Pads/Retro Choir"

Pour chaque sample : le preset .fxp de Surge XT (patches_factory, ou patches_3rdparty/…) est mis dans l'état du VST
(remaster/vststate.py), l'amplitude du pitch bend réglée à ±12 demi-tons, l'état enregistré dans
songs\\vst\\<musique> - <essai>\\. La fiche de la musique est copiée en songs\\<musique> - <essai>.json avec ces samples
en « vsti » (les autres ne changent pas). Le rendu se fait dans out\\Retravaillées\\<musique>\\<essai>\\ (en
reprenant les pistes déjà rendues du remaster) et les MP3 sont posés dans out\\Retravaillées\\<musique>\\, à côté des
autres remasters, pour comparer.

Premier essai fait par Claude, sans écouter (20/11/2026) : c'est à l'utilisateur de juger, et de choisir ensuite
lui-même dans la fenêtre (python -m remaster.choisir).
"""
from __future__ import annotations
import json
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from remaster import render, vst, vststate, paths  # noqa: E402
from remaster.__main__ import open_music  # noqa: E402

SURGE_DATA = ROOT / "tools" / "vst3" / "surge" / "Surge Synth Team" / "SurgeXTData"
BEND = 12


def surge_preset(rel: str) -> pathlib.Path:
    for base in ("patches_factory", "patches_3rdparty"):
        p = SURGE_DATA / base / f"{rel}.fxp"
        if p.exists():
            return p
    raise SystemExit(f"preset Surge XT introuvable : {rel}")


def patch_name(raw: bytes) -> str:
    m = re.search(rb'<meta name="([^"]*)"', vststate.split(raw)[0])
    return m.group(1).decode("utf-8", "replace") if m else "?"


def make_state(plugin: str, preset: str) -> tuple[bytes, str]:
    if plugin != "Surge XT":
        raise SystemExit("pour l'instant, seuls les presets de Surge XT se choisissent sans fenêtre")
    plug = vst.load(plugin)
    plug.raw_state = vststate.with_component(plug.raw_state, vststate.fxp_chunk(surge_preset(preset).read_bytes()))
    plug([], duration=0.25, sample_rate=48000, num_channels=2, reset=False)  # Surge charge le patch ici
    for scene in "ab":
        for d in ("up", "down"):
            setattr(plug, f"{scene}_pitch_bend_{d}_range", f"{BEND} semitones")
    plug([], duration=0.1, sample_rate=48000, num_channels=2, reset=False)
    raw = plug.raw_state
    got = getattr(plug, "a_pitch_bend_up_range")
    if got != f"{BEND} semitones":
        raise SystemExit(f"amplitude du pitch bend non prise : {got}")
    return raw, patch_name(raw)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    music, trial, picks = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3:]
    m = open_music(music)
    cfg = render.load_config(m.cfg_path)
    name = f"{m.name} - {trial}"
    for pick in picks:
        sample, _, spec = pick.partition("=")
        plugin, _, preset = spec.partition(":")
        raw, pname = make_state(plugin, preset)
        rel = f"vst/{name}/s{int(sample):02d}.bin"
        vst.state_path(rel).parent.mkdir(parents=True, exist_ok=True)
        vst.state_path(rel).write_bytes(raw)
        s = cfg["samples"].setdefault(sample, {})
        for k in ("sfz", "program", "soundfont", "fx", "double", "chord", "comment"):
            s.pop(k, None)
        s["vsti"] = {"plugin": plugin, "state": rel, "bend_range": BEND, "preset": preset}
        s["comment"] = f"{plugin}, preset « {pname} » (essai de Claude, sans écoute)"
        print(f"sample {sample} : {plugin} « {pname} »")
    cfg_path = m.cfg_path.with_name(f"{name}.json")
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    base = paths.work_dir(music, m.name)
    work = base / trial
    if (base / "stems").is_dir() and not (work / "stems").exists():
        shutil.copytree(base / "stems", work / "stems")  # les pistes qui ne changent pas ne sont pas refaites
    made = render.remaster(music, cfg, work, original=False, source=m.source, name=name)
    shutil.rmtree(work / "samples", ignore_errors=True)  # déjà dans le dossier de la musique
    for mp3 in made:
        shutil.move(str(mp3), str(base / mp3.name))
        print(f"→ {base / mp3.name}")


if __name__ == "__main__":
    main()
