"""Où vont les fichiers produits : deux dossiers dans out\\ (demande de l'utilisateur, 20/11/2026 : « je m'y perds »).

    out\\Originaux\\<Jeu>\\<musique> (original).mp3   toutes les musiques de chaque jeu, telles quelles
                                                    (scripts/render_originals.py)
    out\\Retravaillées\\<musique>\\                   une musique sur laquelle on travaille : remasters, piano,
                                                    partitions, pistes séparées (stems), samples

Le nom d'une musique contient déjà son jeu (« Dr Mario », « Turrican 3 - world_1 (1) ») : les musiques
retravaillées sont à plat. Le jeu se déduit du chemin de la musique : in\\music\\<Jeu>\\<musique>.mod ou
in\\music\\<Jeu>\\originaux\\<fichier>.
"""
from __future__ import annotations
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
ORIGINALS = OUT / "Originaux"
WORK = OUT / "Retravaillées"


def game_of(music: pathlib.Path) -> str:
    """Le jeu d'une musique, d'après son dossier dans in\\music ; sinon le nom du fichier."""
    p = pathlib.Path(music).resolve()
    for d in p.parents:  # in\music\<Jeu>\originaux\[sous-dossier de l'archive\]<fichier>
        if d.name == "originaux":
            return d.parent.name
    if p.parent.parent.name == "music":
        return p.parent.name
    return p.stem


def game_dir(music: pathlib.Path) -> pathlib.Path:
    """out\\Originaux\\<Jeu>\\ : les MP3 des originaux de toutes les musiques du jeu."""
    return ORIGINALS / game_of(music)


def work_dir(music: pathlib.Path, name: str | None = None) -> pathlib.Path:
    """out\\Retravaillées\\<musique>\\ : ce qu'on fabrique en retravaillant une musique."""
    return WORK / (name or pathlib.Path(music).stem)


def glob_escape(name: str) -> str:
    """Un nom de fichier avec [ ] (« Strider [Custom Version] ») pris tel quel par glob."""
    return "".join(f"[{c}]" if c in "[]*?" else c for c in name)


def copy_original(work: pathlib.Path) -> pathlib.Path | None:
    """Met dans le dossier d'une musique retravaillée le MP3 de son original (demande de l'utilisateur, 20/11/2026 :
    « mets toujours le .mp3 original avec »), copié depuis out\\Originaux\\<Jeu>\\."""
    import shutil
    name = f"{work.name} (original).mp3"
    src = next(iter(sorted(ORIGINALS.glob(f"*/{glob_escape(name)}"))), None)
    if src is None:
        return None
    dest = work / name
    if not dest.exists() or dest.stat().st_mtime < src.stat().st_mtime:
        work.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    return dest
