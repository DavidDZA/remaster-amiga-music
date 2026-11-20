"""Lecteur SFZ : batteries multi-micros au format « ARIA » (Muldjord, Naked Drums, Sonor…), sur une banque fabriquée."""
import math
import mido
import numpy as np
import soundfile as sf
from remaster import sfz

SR = 48000

FILES = {
    "Kit/kit.sfz": """
#include "../Data/macro.txt"
<control> set_hdcc$vol_cm=0.5 set_hdcc$pan_kd=0.5 set_hdcc$wid_oh=1 set_hdcc$bleed=0
#include "../Data/global.txt" #include "../Data/close.txt"
#include "../Data/global.txt" #include "../Data/oh.txt"
""",
    "Data/macro.txt": """
#define $vol_cm 20        #define $pan_kd 31
#define $wid_oh 40        #define $bleed 42
#define $range $level
#define $level 200
""",
    "Data/global.txt": "<global> loop_mode=one_shot\n",
    "Data/close.txt": """
<master> locc$vol_cm=1 amplitude_oncc$vol_cm=200 pan_oncc$pan_kd=100 pan_curvecc$pan_kd=1
<region> key=36 sample=kick_close.wav
<master> locc$bleed=1 amplitude_oncc$bleed=200
<region> key=36 sample=kick_bleed.wav
""",
    "Data/oh.txt": """
<master> pan_oncc$wid_oh=-100 volume_oncc$wid_oh=-6 volume_curvecc$wid_oh=2
<region> key=36 sample=kick_oh.wav
""",
}


def bank(tmp_path):
    def read_text(rel):
        return FILES[rel]

    def fetch(rel):
        p = tmp_path / rel
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            sf.write(p, np.full(SR // 10, 0.5, np.float32), SR)
        return p
    return sfz.Instrument("Kit/kit.sfz", read_text, fetch)


def test_several_includes_and_defines_on_one_line(tmp_path):
    inst = bank(tmp_path)
    assert len(inst.regions) == 3
    assert inst.defines["$pan_kd"] == "31" and inst.defines["$bleed"] == "42"
    assert inst.regions[0]["amplitude_oncc20"] == "200"


def test_set_hdcc_is_a_0_to_1_controller(tmp_path):
    inst = bank(tmp_path)
    assert math.isclose(inst.cc[20], 63.5) and inst.cc[40] == 127 and inst.cc[42] == 0


def test_mics_mixed_by_controllers(tmp_path):
    inst = bank(tmp_path)
    close, bleed, oh = inst.regions
    g, pan = sfz.cc_mods(close, inst.cc)
    assert math.isclose(g, 1.0) and abs(pan) < 1e-9       # 200 % × 0,5 = 100 % ; pan bipolaire au centre
    g, pan = sfz.cc_mods(oh, inst.cc)
    assert math.isclose(g, 1.0) and pan == -100            # largeur à fond : micro de gauche tout à gauche
    v = 100
    assert inst._active(close, v) and not inst._active(bleed, v)  # repisse coupée (set_hdcc = 0)


def test_kit_renders_close_and_overhead_mics(tmp_path):
    inst = bank(tmp_path)
    ev = [(0.0, mido.Message("note_on", channel=9, note=36, velocity=127))]
    a = sfz.render(inst, ev, 0.5, SR)
    assert a[0, 100] > a[1, 100] > 0  # le micro de dessus est à gauche, le micro proche au centre
