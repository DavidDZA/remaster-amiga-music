"""python -m remaster <musique> [--sous-morceau N] [--config songs/<nom>.json] [--out out/Retravaillées/<nom>]

<musique> : un .mod (ProTracker, Soundtracker), ou n'importe quel autre format Amiga (TFMX, David Whittaker,
lecteur propre au jeu…) : ses notes sont alors lues par UADE dans ce que le lecteur envoie à la puce son
(remaster/paula.py). Pour ceux-là, --sous-morceau choisit le morceau (1, 2… comme dans le nom des MP3 de out\\Originaux\\<Jeu>\\).
"""
from __future__ import annotations
import argparse
import dataclasses
import json
import pathlib
import sys
from . import modfile, analyze, render, paths


def draft_config(mod: modfile.Module, title: str) -> dict:
    """Une première fiche d'instruments, à corriger à l'oreille : un piano pour tout ce qui a une hauteur."""
    samples = {}
    for s in mod.samples:
        if len(s.data) < 4:
            continue
        info = analyze.describe(s)
        samples[str(s.index)] = {"name": s.name, "program": 0,
                                 "comment": f"{info['durée_s']} s, note au C-2 : {info['note_au_C2']}"}
    return {"title": title, "artist": "", "soundfont": "GeneralUser-GS.sf2", "samples": samples}


def is_protracker(path: pathlib.Path) -> bool:
    try:
        modfile.load(path)
        return True
    except (ValueError, IndexError, OSError):
        return False


def uade_name(path: pathlib.Path, number: int | None, count: int) -> str:
    """Même nom que scripts/render_originals.py : « <Jeu> - <titre> (n) » pour in\\music\\<Jeu>\\originaux\\<fichier>."""
    sys.path.insert(0, str(render.ROOT / "scripts"))
    import import_lha  # noqa: PLC0415
    from .paths import game_of
    game = game_of(path)
    name = f"{game} - {import_lha.uade_title(path)}"
    return name if count <= 1 else f"{name} ({number or 1})"


@dataclasses.dataclass
class Music:
    mod: modfile.Module
    song: object             # player.Song
    source: tuple | None     # (Module, Song, WAV d'origine) pour une musique lue par UADE, sinon None
    name: str                # nom des fichiers produits et de la fiche
    out_dir: pathlib.Path
    cfg_path: pathlib.Path


def open_music(path: pathlib.Path, sous_morceau: int | None = None, max_s: int = 300,
               out: pathlib.Path | None = None, config: pathlib.Path | None = None, log=print) -> Music:
    """Lit une musique (.mod, ou tout autre format par UADE) ; crée sa fiche d'instruments si elle n'existe pas."""
    source, name = None, path.stem
    if is_protracker(path):
        from . import player
        mod = modfile.load(path)
        song = player.play(mod)
        title = mod.title or path.stem
        out_dir = out or paths.work_dir(path, name)
    else:
        from . import paula
        lo, hi = paula.subsongs(path)
        number = sous_morceau or 1
        if not lo <= lo + number - 1 <= hi:
            raise SystemExit(f"{path.name} a {hi - lo + 1} morceau(x) : --sous-morceau entre 1 et {hi - lo + 1}")
        name = uade_name(path, number, hi - lo + 1)
        out_dir = out or paths.work_dir(path, name)
        log(f"Lecture des notes avec UADE : {path.name}, morceau {number}/{hi - lo + 1}…")
        mod, song, info = paula.load(path, lo + number - 1, max_s, keep=out_dir)
        log(f"  {info.get('player', '?')} : {len(mod.samples)} samples, "
            f"{sum(t.trigger for ch in song.ticks for t in ch)} notes, {song.duration:.0f} s")
        source = (mod, song, out_dir / "uade.wav")
        title = name
    cfg_path = config or render.ROOT / "songs" / f"{name}.json"
    if not cfg_path.exists():
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(json.dumps(draft_config(mod, title), ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"Fiche d'instruments créée : {cfg_path} (à compléter, puis relancer)")
    return Music(mod, song, source, name, out_dir, cfg_path)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Remasterise une musique Amiga en MP3 avec des instruments modernes.")
    ap.add_argument("mod", type=pathlib.Path)
    ap.add_argument("--sous-morceau", type=int, help="pour un format autre que .mod : n° du morceau (1, 2…)")
    ap.add_argument("--max", type=int, default=300, help="durée maximale (secondes) pour un format autre que .mod")
    ap.add_argument("--config", type=pathlib.Path, help="fiche des instruments (JSON) ; par défaut songs/<nom>.json")
    ap.add_argument("--out", type=pathlib.Path, help="dossier de travail ; par défaut out/Retravaillées/<nom>")
    ap.add_argument("--no-original", action="store_true", help="ne pas refaire le MP3 de l'original")
    a = ap.parse_args()
    m = open_music(a.mod, a.sous_morceau, a.max, a.out, a.config)
    cfg = render.load_config(m.cfg_path)
    render.remaster(a.mod, cfg, m.out_dir, original=not a.no_original, source=m.source, name=m.name)
    if m.source is not None:
        (m.source[2]).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
