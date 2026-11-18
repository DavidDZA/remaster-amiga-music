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


def boucle(intro: int, motif: list[int], tours: int, pas: float = 0.25):
    """Journal d'une musique : `intro` notes, puis `motif` (périodes) répété `tours` fois sur la voie 0."""
    rows, t = [], 0.0
    pers = [300 + i for i in range(intro)] + motif * tours
    for p in pers:
        rows += [(t, 0, paula.LEN, 50), (t, 0, paula.LCH, 0), (t, 0, paula.LCL, 0x1000), (t, 0, paula.PER, p),
                 (t, 0, paula.LOOP, 0)]
        t += pas
    return journal(rows)


def test_boucle_trouvee():
    ev = boucle(intro=8, motif=list(range(400, 432)), tours=5)  # tour de 32 notes différentes = 8 s
    a, length = paula.find_loop(ev)
    assert a == pytest.approx(8 * 0.25) and length == pytest.approx(8.0)


def test_pas_de_boucle():
    ev = journal([(i * 0.25, 0, k, v) for i in range(200) for k, v in ((paula.LEN, 50), (paula.PER, 300 + i),
                                                                       (paula.LOOP, 0))])
    assert paula.find_loop(ev) is None


def test_une_ou_deux_fois_la_boucle():
    import importlib.util
    spec = importlib.util.spec_from_file_location("r", ROOT / "scripts" / "render_originals.py")
    r = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(r)
    sr = 100
    x = np.ones((sr * 600, 2), np.float32)
    # tour de 80 s après 10 s d'intro : 90 s < 2 min → deux tours (170 s) + fondu
    ev = boucle(intro=40, motif=list(range(500, 820)), tours=6)          # 320 notes × 0,25 s = 80 s
    y, how = r.cut_at_loop(x, sr, ev, natural_end=False)
    assert how == "boucle 2 fois" and len(y) / sr == pytest.approx(10 + 160 + r.FADE, abs=0.1)
    assert y[-1, 0] == pytest.approx(0, abs=0.02)                       # fin en fondu
    # tour de 150 s : un seul
    ev = boucle(intro=0, motif=list(range(500, 1100)), tours=3)          # 600 notes × 0,25 s = 150 s
    y, how = r.cut_at_loop(x, sr, ev, natural_end=False)
    assert how == "boucle 1 fois" and len(y) / sr == pytest.approx(150 + r.FADE, abs=0.1)
    # morceau qui s'arrête de lui-même : intact
    y, how = r.cut_at_loop(x[:sr * 90], sr, ev, natural_end=True)
    assert len(y) == sr * 90


def test_boucle_avec_quelques_notes_au_hasard():
    # 40 tours d'un motif de 40 notes ; dans 2 tours, une note change (roulement tiré au sort) : 0,1 % des notes
    motif = list(range(500, 540))
    pers = motif * 40
    pers[40 * 7 + 5] = 999
    pers[40 * 23 + 17] = 998
    rows, t = [], 0.0
    for p in pers:
        rows += [(t, 0, paula.LEN, 50), (t, 0, paula.PER, p), (t, 0, paula.LOOP, 0)]
        t += 0.25
    a, length = paula.find_loop(journal(rows))
    assert a == pytest.approx(0) and length == pytest.approx(10.0)


def test_changement_de_partie_n_est_pas_une_boucle():
    # A A A A B B B B C D E F… : le motif de 10 s ne se répète pas jusqu'à la fin
    a_part, b_part = list(range(500, 540)), list(range(600, 640))
    pers = a_part * 4 + b_part * 4 + list(range(700, 1100))
    rows, t = [], 0.0
    for p in pers:
        rows += [(t, 0, paula.LEN, 50), (t, 0, paula.PER, p), (t, 0, paula.LOOP, 0)]
        t += 0.25
    assert paula.find_loop(journal(rows)) is None
