"""python -m remaster "morceau.mod" [--config songs/morceau.json] [--out out/morceau]"""
from __future__ import annotations
import argparse
import json
import pathlib
from . import modfile, analyze, render


def draft_config(mod_path: pathlib.Path) -> dict:
    """Une première fiche d'instruments, à corriger à l'oreille : un piano pour tout ce qui a une hauteur."""
    mod = modfile.load(mod_path)
    samples = {}
    for s in mod.samples:
        if len(s.data) < 4:
            continue
        info = analyze.describe(s)
        samples[str(s.index)] = {"name": s.name, "program": 0,
                                 "comment": f"{info['durée_s']} s, note au C-2 : {info['note_au_C2']}"}
    return {"title": mod.title or mod_path.stem, "artist": "", "soundfont": "GeneralUser-GS.sf2", "samples": samples}


def main():
    ap = argparse.ArgumentParser(description="Remasterise un module Amiga (.mod) en MP3 avec des instruments modernes.")
    ap.add_argument("mod", type=pathlib.Path)
    ap.add_argument("--config", type=pathlib.Path, help="fiche des instruments (JSON) ; par défaut songs/<nom>.json")
    ap.add_argument("--out", type=pathlib.Path, help="dossier de sortie ; par défaut out/<nom>")
    ap.add_argument("--no-original", action="store_true", help="ne pas refaire le MP3 de l'original")
    a = ap.parse_args()
    cfg_path = a.config or render.ROOT / "songs" / f"{a.mod.stem}.json"
    if not cfg_path.exists():
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(json.dumps(draft_config(a.mod), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Fiche d'instruments créée : {cfg_path} (à compléter, puis relancer)")
    cfg = render.load_config(cfg_path)
    render.remaster(a.mod, cfg, a.out or render.ROOT / "out" / a.mod.stem, original=not a.no_original)


if __name__ == "__main__":
    main()
