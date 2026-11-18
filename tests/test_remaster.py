import pathlib
import math
import struct
import mido
import numpy as np
import pytest
from remaster import modfile, player, midi, analyze, extras

ROOT = pathlib.Path(__file__).resolve().parent.parent
MOD = ROOT / "in" / "mod" / "Dr Mario" / "Dr Mario.mod"


@pytest.fixture(scope="module")
def mod():
    return modfile.load(MOD)


@pytest.fixture(scope="module")
def song(mod):
    return player.play(mod)


def test_lecture_du_module(mod):
    assert mod.channels == 4
    assert mod.title == "friend or fom"
    assert len(mod.orders) == 54
    assert len(mod.patterns) == 31
    assert len(mod.samples[0].data) == 4002
    assert len(mod.samples[3].data) == 0  # sample vide, sert à couper une voie


def test_duree_comme_openmpt(song):
    # openmpt123 donne 6 min 10,6 s pour ce module
    assert abs(song.duration - 370.6) < 0.5


def test_hauteur_des_samples(mod):
    assert round(analyze.root_midi(mod.samples[2])) == 32  # basse : G#1 au C-2
    assert round(analyze.root_midi(mod.samples[4])) == 60  # lead : C4
    assert round(analyze.root_midi(mod.samples[11])) == 48  # guitare : C3


def test_glissando_en_pitch_bend(song):
    inst = midi.Instrument(program=30, root=60)
    ev = midi.route_events(song, 5, 2, inst)  # lead sur la voie 3 : effets 1xx / 2xx
    bends = [m.pitch for _, m in ev if m.type == "pitchwheel"]
    assert len(set(bends)) > 10
    assert all(-8192 <= b <= 8191 for b in bends)


def test_power_chord_et_notes_fermees(song):
    inst = midi.Instrument(program=30, root=48, chord=[0, 7, 12])
    ev = midi.route_events(song, 12, 1, inst)
    ons = [m for _, m in ev if m.type == "note_on"]
    offs = [m for _, m in ev if m.type == "note_off"]
    assert len(ons) == len(offs) and len(ons) % 3 == 0
    t0 = min(t for t, m in ev if m.type == "note_on")
    first = sorted(m.note for t, m in ev if m.type == "note_on" and t == t0)
    assert first[1] - first[0] == 7 and first[2] - first[0] == 12


def test_batterie_et_volume(song):
    inst = midi.Instrument(drum=36, velocity=120)
    ev = midi.route_events(song, 1, 0, inst)
    ons = [m for _, m in ev if m.type == "note_on"]
    assert ons and all(m.channel == 9 and m.note == 36 for m in ons)


def test_ajouts_de_batterie(song, mod):
    drows = extras.drum_rows(song, {1, 2})
    hats = extras.hihat_events(song, mod, drows, {"every_rows": 2})
    crashes = extras.crash_rows(song, mod, drows)
    assert len(hats) > 1000 and 10 < len(crashes) < 60
    # pas de charleston en même temps qu'une crash
    crash_times = {song.rows[i][2] for i in crashes}
    assert not any(m.type == "note_on" and t in crash_times for t, m in hats)


def test_fichier_midi_combine(song, mod):
    from remaster import render
    cfg = render.load_config(ROOT / "songs" / "Dr Mario.json")
    rts = render.routes(song, mod, cfg)
    # parties doublées : une piste à gauche (G), une à droite (D), chacune la moitié du sample d'origine
    doubled = [r for r in rts if r[0] == 12]
    assert {r[2].part for r in doubled} == {"G", "D"}
    assert all(r[2].share == 0.5 for r in doubled)
    left = next(r for r in doubled if r[2].part == "G" and r[1] == 1)
    right = next(r for r in doubled if r[2].part == "D" and r[1] == 1)
    assert left[2].sfz != right[2].sfz and left[2].pan == -right[2].pan
    assert left[2].fx != right[2].fx  # un autre ampli à droite
    delay = cfg["samples"]["12"]["double"].get("delay_ms", 12) / 1000
    assert abs(right[3][0][0] - left[3][0][0] - delay) < 1e-9
    mf = midi.combined(song, [r for r in rts if r[2].part != "D"])
    assert mf is not None
    assert abs(mf.length - (song.duration + midi.TAIL)) < 1.0


def test_cache_des_pistes_ignore_le_mixage():
    from remaster import render
    chain = [{"type": "HighpassFilter", "cutoff_frequency_hz": 100}, {"type": "nam", "model": "x"},
             {"type": "cab", "ir": "y"}, {"type": "PeakFilter", "cutoff_frequency_hz": 3000, "gain_db": -3}]
    heavy, light = render.split_fx(chain)
    assert [f["type"] for f in heavy] == ["HighpassFilter", "nam", "cab"] and light == chain[3:]
    ev = [(0.0, mido.Message("note_on", note=40, velocity=100))]
    a = midi.Instrument(name="a", fx=chain, pan=-1, gain_db=0)
    b = midi.Instrument(name="b", fx=chain[:3] + [{"type": "LowpassFilter", "cutoff_frequency_hz": 8000}], pan=1, gain_db=-6)
    c = midi.Instrument(name="a", fx=chain, velocity=90)
    key = lambda i: render._part_key("s", ev, i, 10.0, 0, "sf")
    assert key(a) == key(b)  # EQ après l'ampli, panoramique, volume : pas de nouveau rendu
    assert key(a) != key(c)  # vélocité : le son change


def _soundtracker_bytes(extra_orders=b"") -> bytes:
    """Un petit module Soundtracker 15 samples : 1 pattern, une note sur la voie 1, un sample de 64 octets."""
    d = bytearray(b"st15 test".ljust(20, b"\0"))
    for i in range(15):
        name = f"smp{i + 1}".encode().ljust(22, b"\0")
        ln = 32 if i == 0 else 0  # en mots de 2 octets
        d += name + struct.pack(">HBBHH", ln, 0, 64 if i == 0 else 0, 0, 1)
    d += bytes([1, 120]) + (b"\0" + extra_orders).ljust(128, b"\0")
    pattern = bytearray(1024)
    pattern[0:4] = bytes([0x01, 0xAC, 0x10, 0x00])  # C-2 (période 428), sample 1
    d += pattern + bytes(range(64))
    return bytes(d)


def test_module_soundtracker_15_samples(tmp_path):
    p = tmp_path / "st.mod"
    p.write_bytes(_soundtracker_bytes())
    m = modfile.load(p)
    assert m.channels == 4 and len(m.samples) == 15 and m.orders == [0]
    assert m.patterns[0][0][0].period == 428 and m.patterns[0][0][0].sample == 1
    assert len(m.samples[0].data) == 64
    assert player.play(m).duration > 0


def test_soundtracker_restes_dans_l_ordre(tmp_path):
    # un rip qui laisse des numéros de patterns après la fin du morceau (Operation Wolf) : on compte 1 pattern
    p = tmp_path / "st.mod"
    p.write_bytes(_soundtracker_bytes(extra_orders=bytes([9, 14])))
    assert modfile.soundtracker_patterns(p.read_bytes()) == 1
    assert len(modfile.load(p).patterns) == 1


def test_pas_un_module(tmp_path):
    assert not modfile.is_soundtracker(bytes(range(256)) * 20)
