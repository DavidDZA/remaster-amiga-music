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
