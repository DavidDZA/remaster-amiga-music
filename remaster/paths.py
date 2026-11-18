"""Où vont les fichiers produits.

    out\\<Jeu>\\<musique> (original).mp3      toutes les musiques du jeu, à plat (scripts/render_originals.py)
    out\\<Jeu>\\<musique>\\                    seulement pour une musique qu'on retravaille : remasters, piano,
                                             partitions, pistes séparées (stems), samples

Le jeu se déduit du chemin de la musique : in\\music\\<Jeu>\\<musique>.mod ou in\\music\\<Jeu>\\originaux\\<fichier>.
"""
from __future__ import annotations
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "out"


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
    """out\\<Jeu>\\ : les MP3 des originaux de toutes les musiques du jeu."""
    return OUT / game_of(music)


def work_dir(music: pathlib.Path, name: str | None = None) -> pathlib.Path:
    """out\\<Jeu>\\<musique>\\ : ce qu'on fabrique en retravaillant une musique."""
    return game_dir(music) / (name or pathlib.Path(music).stem)
