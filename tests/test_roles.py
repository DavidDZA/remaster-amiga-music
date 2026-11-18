"""Rôles des samples (remaster/roles.py), hauteur des sons de synthé courts, grille des musiques lues par UADE."""
import numpy as np
import pytest
from remaster import roles, analyze, paula
from remaster.modfile import Sample, Module
from remaster.player import Song, Tick


def test_bruit_et_note_pure():
    t = np.arange(4096)
    pure = (60 * np.sin(2 * np.pi * t / 32)).astype(np.int8)
    bruit = np.random.default_rng(1).integers(-100, 100, 4096).astype(np.int8)
    assert roles.flatness(pure) < 0.1 < 0.35 < roles.flatness(bruit)


def test_hauteur_d_un_son_de_synthe_court():
    onde = (60 * np.sign(np.sin(2 * np.pi * np.arange(32) / 32))).astype(np.int8)  # une période de 32 octets
    s = Sample(1, "synthé", onde, 0, 64, 0, 32)
    # 8 287 Hz / 32 ≈ 259 Hz : do 4 (MIDI 60)
    assert round(analyze.root_midi(s)) == 60


def chanson(notes, frames):
    """notes : {voie: [(trame, sample, période)]}."""
    ticks = []
    for c in range(4):
        by = {f: (s, p) for f, s, p in notes.get(c, [])}
        ch, cur = [], (0, 0)
        for f in range(frames):
            trig = f in by
            if trig:
                cur = by[f]
            ch.append(Tick(f * 0.02, cur[0], float(cur[1]), 64, trig, cur[1]))
        ticks.append(ch)
    return Song(4, ticks, [f * 0.02 for f in range(frames)], frames * 0.02, [(0, 0, 0.0)])


def test_grille_et_premier_temps():
    # croches toutes les 8 trames ; une note longue (32 trames) toutes les 128 trames, à partir de la trame 20
    mel = [(f, 1, 400) for f in range(4, 1000, 8) if (f - 20) % 128 >= 32]
    mel += [(f, 1, 300) for f in range(20, 1000, 128)]
    song = chanson({0: sorted(mel)}, 1000)
    data = np.zeros(4000, np.int8)
    mod = Module("t", 4, [Sample(1, "s", data, 0, 64, 0, 0)], [0], 0, [])
    ev = (np.array([0.0]), np.array([0]), np.array([0]), np.array([0]))  # pas de boucle
    mod2, song2, info = paula.on_grid(mod, song, ev)
    assert info["ligne_s"] == pytest.approx(0.08)            # croche = 8 trames : une ligne = 4 trames
    assert info["noire_bpm"] == 188
    # la note longue tombe sur un premier temps : ligne multiple de 16
    t_long = 20 * 0.02 + info["decalage_s"]
    assert round(t_long / info["ligne_s"]) % 16 == 0
