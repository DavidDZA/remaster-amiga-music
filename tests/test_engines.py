"""Lecteur SFZ et ampli NAM, sur de petites données fabriquées (sans réseau)."""
import pathlib
import random
import mido
import numpy as np
import pytest
import soundfile as sf
from remaster import sfz, nam, fx

SR = 48000


def make_bank(tmp_path, files: dict[str, str]):
    """Une banque SFZ en mémoire ; chaque sample est une sinusoïde dont la fréquence code la note et la couche."""
    def read_text(rel):
        return files[rel]

    def fetch(rel):
        p = tmp_path / rel
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            t = np.arange(SR) / SR
            freq = 100 + 10 * (sum(map(ord, rel)) % 50)
            sf.write(p, (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32), SR)
        return p
    return read_text, fetch


BANK = {
    "Programs/main.sfz": """
#define $KEY 60
<control> set_cc7=100
<global> ampeg_release=0.1
<group> lovel=1 hivel=63
#include "maps/soft.sfz"
<group> lovel=64 hivel=127
<region> sample=../Samples/loud_rr1.wav key=$KEY seq_length=2 seq_position=1
<region> sample=../Samples/loud_rr2.wav key=$KEY seq_length=2 seq_position=2
<region> sample=../Samples/hidden.wav key=$KEY locc7=120
<group> group=2 off_by=3 loop_mode=one_shot
<region> sample=../Samples/open hat.wav key=46
<group> group=3
<region> sample=../Samples/closed.wav key=42
""",
    "Programs/maps/soft.sfz": "<region> sample=../Samples/soft.wav lokey=48 hikey=72 pitch_keycenter=60 // commentaire\n",
}


def test_sfz_parse_include_define_et_conditions(tmp_path):
    read_text, fetch = make_bank(tmp_path, BANK)
    inst = sfz.Instrument("Programs/main.sfz", read_text, fetch)
    assert len(inst.regions) == 6
    assert inst.cc[7] == 100
    rng = random.Random(0)
    counters = {}
    soft = inst.pick(60, 30, counters, rng)
    assert [r["sample"] for r, _, _ in soft] == ["../Samples/soft.wav"]
    # couche forte : prises alternées, et la région cachée (locc7=120) jamais jouée
    a = inst.pick(60, 100, counters, rng)
    b = inst.pick(60, 100, counters, rng)
    names = {a[0][0]["sample"], b[0][0]["sample"]}
    assert names == {"../Samples/loud_rr1.wav", "../Samples/loud_rr2.wav"}
    assert inst.sample_path(a[0][0]).startswith("Samples/")
    assert inst.sample_path(inst.regions[4]) == "Samples/open hat.wav"  # espace dans le nom de fichier


def test_sfz_note_hors_tessiture_transposee(tmp_path):
    read_text, fetch = make_bank(tmp_path, BANK)
    inst = sfz.Instrument("Programs/main.sfz", read_text, fetch)
    picked = inst.pick(80, 30, {}, random.Random(0))  # au-dessus de la tessiture (48-72)
    assert len(picked) == 1 and picked[0][1] == 80 - 72 and picked[0][2] == 72


def test_sfz_rendu_bend_et_coupure(tmp_path):
    read_text, fetch = make_bank(tmp_path, BANK)
    inst = sfz.Instrument("Programs/main.sfz", read_text, fetch)
    ev = [(0.0, mido.Message("note_on", note=60, velocity=30)),
          (0.5, mido.Message("note_off", note=60)),
          (1.0, mido.Message("note_on", note=46, velocity=100)),   # charleston ouvert (one_shot)
          (1.2, mido.Message("note_on", note=42, velocity=100))]   # le fermé coupe l'ouvert
    y = sfz.render(inst, ev, 2.0, SR)
    assert y.shape[0] == 2
    rms = lambda a, b: float(np.sqrt(np.mean(y[:, int(a * SR):int(b * SR)] ** 2)))
    assert rms(0.1, 0.4) > 0.005         # la note sonne (douce : vélocité 30)
    assert rms(0.75, 0.95) < 1e-3        # relâchée (release 0,1 s)
    assert rms(1.05, 1.15) > 0.05        # charleston ouvert
    # après 1,2 s il ne reste que le fermé : comparer avec le fermé seul
    y2 = sfz.render(inst, ev[3:], 2.0, SR)
    assert np.allclose(y[:, int(1.25 * SR):int(1.5 * SR)], y2[:, int(1.25 * SR):int(1.5 * SR)], atol=1e-3)


def tiny_nam():
    cfg = {"layers": [
        {"input_size": 1, "condition_size": 1, "head_size": 2, "channels": 3, "kernel_size": 3,
         "dilations": [1, 2], "activation": "Tanh", "gated": False, "head_bias": False},
        {"input_size": 3, "condition_size": 1, "head_size": 1, "channels": 2, "kernel_size": 3,
         "dilations": [1, 2], "activation": "Tanh", "gated": False, "head_bias": True}]}
    n1 = 1 * 3 + 2 * (3 * 3 * 3 + 3 + 3 + 9 + 3) + 2 * 3
    n2 = 3 * 2 + 2 * (2 * 2 * 3 + 2 + 2 + 4 + 2) + 1 * 2 + 1
    w = np.random.default_rng(1).normal(0, 0.5, n1 + n2 + 1)
    return cfg, w


def test_nam_poids_causalite_et_silence():
    cfg, w = tiny_nam()
    with pytest.raises(ValueError):
        nam.WaveNet(cfg, w[:-1])
    net = nam.WaveNet(cfg, w)
    assert net.receptive == 1 + 2 * 3 + 2 * 3
    x = np.zeros(4000, np.float32)
    x[1000:3000] = np.sin(np.arange(2000) / 7).astype(np.float32)
    y = net.process(x, block=512)
    y_full = net._run(np.concatenate([np.zeros(net.receptive, np.float32), x]))[net.receptive:]
    assert np.allclose(y, y_full, atol=1e-5)  # le découpage en blocs et le saut des silences ne changent rien
    x2 = x.copy()
    x2[2000:] = 0
    y2 = net.process(x2, block=512)
    assert np.allclose(y[:2000], y2[:2000], atol=1e-6)  # causal : le futur ne change pas le passé


def test_chaine_effets_melange():
    x = np.random.default_rng(0).normal(0, 0.1, (2, SR)).astype(np.float32)
    y = fx.apply(x, [{"type": "gain", "db": -6.0206, "mix": 0.5}], SR)
    assert np.allclose(y, x * 0.75, atol=1e-4)
    z = fx.apply(x, [{"type": "LowpassFilter", "cutoff_frequency_hz": 1000}], SR)
    assert z.shape == x.shape and np.std(z) < np.std(x)


def test_sfz_etouffement(tmp_path):
    read_text, fetch = make_bank(tmp_path, BANK)
    inst = sfz.Instrument("Programs/main.sfz", read_text, fetch)
    ev = [(0.0, mido.Message("note_on", note=55, velocity=30)),
          (0.5, mido.Message("note_on", note=60, velocity=30)),   # nouvelle attaque : la première note se tait
          (0.5, mido.Message("note_on", note=64, velocity=30)),   # même instant : accord, les deux sonnent
          (1.5, mido.Message("note_off", note=60)), (1.5, mido.Message("note_off", note=64)),
          (1.5, mido.Message("note_off", note=55))]
    alone = sfz.render(inst, [ev[0], ev[5]], 2.0, SR)
    both = sfz.render(inst, ev, 2.0, SR, choke=True)
    chord = sfz.render(inst, ev[1:5], 2.0, SR)
    w = slice(int(0.6 * SR), int(1.4 * SR))
    assert np.allclose(both[:, w], chord[:, w], atol=1e-4)  # après 0,5 s il ne reste que l'accord
    assert np.sqrt(np.mean(alone[:, w] ** 2)) > 0.003        # sans étouffement, la première note sonnerait encore


def test_doublons_du_module():
    from remaster import modfile, player, render
    mod = modfile.load(pathlib.Path(__file__).resolve().parent.parent / "Dr Mario.mod")
    song = player.play(mod)
    d = render.duplicates(song, 12, 2)   # voie 3 : souvent les mêmes accords que la voie 2
    assert 150 < len(d) < 300
    assert render.duplicates(song, 12, 0) == set()  # la première voie n'est jamais un doublon


def test_echo_dose_une_seule_fois():
    x = np.zeros((2, SR), np.float32)
    x[:, 0] = 1.0
    y = fx.apply(x, [{"type": "Delay", "delay_seconds": 0.25, "feedback": 0.0, "mix": 0.2}], SR)
    assert abs(y[0, 0] - 0.8) < 1e-3                        # son direct : 80 %
    assert abs(y[0, int(0.25 * SR)] - 0.2) < 2e-2            # écho : 20 % (pas 10 %)
