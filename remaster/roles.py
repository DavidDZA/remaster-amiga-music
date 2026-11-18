"""Reconnaît le rôle de chaque sample (batterie, basse, mélodie) pour écrire une première fiche piano.

Pour chaque sample, d'après ses notes et son son :
- **batterie** : un ou deux sons de hauteur fixe (pas une onde pure) sur au moins 8 coups, ou un son de bruit
  (spectre plat) à 4 hauteurs au plus ;
- **basse** : parmi les autres qui jouent au moins 16 notes, le plus grave (médiane sous le mi 3) ;
- **mélodie** : tout le reste ; la partie « Mélodie » prend, à chaque mesure, la voie qui joue le plus haut.
Les samples presque muets (moins de 4 notes) sont ignorés.

C'est une estimation : la fiche écrite (songs\\<musique>.json) se corrige à la main, comme celle de Dr Mario.
"""
from __future__ import annotations
import numpy as np
from .modfile import Module, period_to_semitones
from .player import Song
from . import analyze


def flatness(data: np.ndarray) -> float:
    """Platitude du spectre (0 : une note pure ; vers 1 : du bruit, comme une caisse claire ou une cymbale)."""
    x = data.astype(np.float32)
    if len(x) < 64:
        return 0.0
    x = x[: min(len(x), 8192)] * np.hanning(min(len(x), 8192))
    sp = np.abs(np.fft.rfft(x)) + 1e-9
    return float(np.exp(np.mean(np.log(sp))) / np.mean(sp))


def stats(mod: Module, song: Song) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for c, ticks in enumerate(song.ticks):
        for t in ticks:
            if t.trigger and t.sample:
                d = out.setdefault(t.sample, {"notes": 0, "periods": set(), "pitches": [], "channels": set()})
                d["notes"] += 1
                d["periods"].add(round(t.note_period))
                d["channels"].add(c)
                s = mod.samples[t.sample - 1]
                root = analyze.root_midi(s)
                if root is not None and t.note_period:
                    d["pitches"].append(root + period_to_semitones(t.note_period))
    for idx, d in out.items():
        s = mod.samples[idx - 1]
        d["flat"] = flatness(s.data)
        d["median"] = float(np.median(d["pitches"])) if d["pitches"] else None
    return out


def guess(mod: Module, song: Song) -> dict[int, str]:
    """{n° de sample: « batterie » | « basse » | « mélodie » | « ignoré »}."""
    st = stats(mod, song)
    roles = {}
    for idx, d in st.items():
        if d["notes"] < 4 or d["median"] is None and len(d["periods"]) <= 1:
            roles[idx] = "ignoré"
        elif (len(d["periods"]) <= 2 and d["notes"] >= 8 and d["flat"] > 0.15) or                 (d["flat"] > 0.35 and len(d["periods"]) <= 4):
            # batterie : un ou deux sons fixes qui ne sont pas une onde pure, ou un bruit à peu de hauteurs (un son
            # un peu bruité qui joue beaucoup de hauteurs est un instrument : basse ou lead saturés)
            roles[idx] = "batterie"
    pitched = [(d["median"], idx) for idx, d in st.items() if idx not in roles and d["median"] is not None]
    for _m, idx in pitched:
        roles[idx] = "mélodie"
    candidates = [(m, idx) for m, idx in pitched if st[idx]["notes"] >= 16]
    if len(pitched) > 1 and candidates:
        low, idx = min(candidates)
        if low < 52:
            roles[idx] = "basse"
    for idx in st:
        roles.setdefault(idx, "ignoré")
    return roles


def piano_config(mod: Module, song: Song, title: str) -> dict:
    """Une fiche d'instruments pour le piano, d'après les rôles reconnus."""
    st = stats(mod, song)
    roles = guess(mod, song)
    samples = {}
    for idx in sorted(st):
        d, role = st[idx], roles[idx]
        med = analyze.note_name(d["median"]) if d["median"] is not None else "?"
        samples[str(idx)] = {
            "name": role.capitalize(),
            "comment": f"rôle deviné : {role} ({d['notes']} notes, {len(d['periods'])} hauteurs, médiane {med}, "
                       f"voies {sorted(c + 1 for c in d['channels'])}, bruit {d['flat']:.2f})"}
        if role == "batterie":
            samples[str(idx)]["drum"] = 38
        if role == "ignoré":
            samples[str(idx)]["mute"] = True
    melody = [i for i, r in roles.items() if r == "mélodie"]
    bass = [i for i, r in roles.items() if r == "basse"]
    return {
        "title": title, "artist": "", "soundfont": "GeneralUser-GS.sf2",
        "comment": "fiche automatique (remaster/roles.py) : à vérifier et corriger à l'oreille",
        "samples": samples,
        "partitions": {"Mélodie": {"instrument": "guitare", "samples": sorted(melody), "lead": True}},
        "piano": {"melody": "Mélodie", "chords": [], "riff": [], "bass": sorted(bass),
                  "harmony": sorted(i for i, r in roles.items() if r in ("mélodie", "basse"))},
    }
