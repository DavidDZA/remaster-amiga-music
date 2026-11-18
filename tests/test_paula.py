"""Notes lues dans le journal de la puce son Paula (remaster/paula.py)."""
import pathlib
import numpy as np
import pytest
from remaster import paula, modfile, player

ROOT = pathlib.Path(__file__).resolve().parent.parent
MOD = ROOT / "in" / "music" / "Dr Mario" / "Dr Mario.mod"
needs_uade = pytest.mark.skipif(not (paula.UADE / "bin" / "uadecore.exe").exists(),
                                reason="UADE absent (scripts/build_uade.py)")


def journal(rows):
    """rows : [(temps, voie, type, valeur)] → le format de paula.events()."""
    t, c, k, v = zip(*rows)
    return np.array(t, float), np.array(c), np.array(k), np.array(v)


def test_une_note_sans_boucle():
    ev = journal([(0.1, 0, paula.LEN, 100), (0.1, 0, paula.LCH, 0), (0.1, 0, paula.LCL, 0x1000),
                  (0.1, 0, paula.PER, 428), (0.1, 0, paula.VOL, 64), (0.1, 0, paula.LOOP, 0),
                  (0.101, 0, paula.LEN, 1)])
    smp = {(0x1000, 200): bytes(range(200))}
    mod, song = paula.to_song(ev, smp, 1.0)
    trig = [t for t in song.ticks[0] if t.trigger]
    assert len(trig) == 1 and trig[0].sample == 1 and trig[0].period == 428 and trig[0].volume == 64
    assert abs(trig[0].time - 0.1) < 0.021
    assert len(mod.samples) == 1 and len(mod.samples[0].data) == 200
    # sans boucle, la note s'arrête à la fin du sample : 200 octets à la période 428 (≈ 8 287 Hz) ≈ 24 ms
    assert song.ticks[0][-1].sample == 0


def test_sample_vide_coupe_la_voie():
    ev = journal([(0.0, 1, paula.LEN, 1), (0.0, 1, paula.LCH, 0), (0.0, 1, paula.LCL, 0x2000),
                  (0.0, 1, paula.PER, 300), (0.0, 1, paula.LOOP, 0)])
    mod, song = paula.to_song(ev, {(0x2000, 2): b"\0\0"}, 0.5)
    assert not any(t.trigger for t in song.ticks[1]) and not mod.samples


def test_temps_zero_sur_la_premiere_note():
    ev = journal([(0.3, 0, paula.VOL, 0), (0.32, 2, paula.LOOP, 0), (0.5, 2, paula.LOOP, 0)])
    (times, *_), shift = paula.align(ev)
    assert shift == pytest.approx(0.32) and times[1] == 0 and times[2] == pytest.approx(0.18)


@needs_uade
def test_dr_mario_comme_le_lecteur_protracker():
    mod, song, info = paula.load(MOD, seconds=40)
    ref = player.play(modfile.load(MOD))
    for c in range(4):
        got = {round(t.time / 0.02): (t.sample, round(t.note_period)) for t in song.ticks[c] if t.trigger
               and t.time < 38}
        exp = {round(t.time / 0.02): (t.sample, t.note_period) for t in ref.ticks[c] if t.trigger and t.time < 38}
        assert set(got) == set(exp)                                    # mêmes instants
        assert all(got[k][1] == exp[k][1] for k in exp)                # mêmes hauteurs
        pairs = {(got[k][0], exp[k][0]) for k in exp}
        assert len({a for a, _ in pairs}) == len(pairs)                # un sample UADE = un sample du module
