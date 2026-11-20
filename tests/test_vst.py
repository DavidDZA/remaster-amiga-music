"""VST3 : recherche des plugins, catalogue, messages envoyés au synthé, extrait en boucle, rendu d'une piste.

Le rendu avec un vrai VST (Surge XT) est sauté s'il n'est pas dans tools/vst3 (scripts/setup_tools.py).
"""
import json
import pathlib
import mido
import numpy as np
import pytest
from remaster import vst, midi, render
from remaster.choisir import excerpt


def note(t, n, v=100):
    return (t, mido.Message("note_on", note=n, velocity=v))


def test_bend_rescaled_to_synth_range():
    ev = [(0.0, mido.Message("pitchwheel", pitch=round(1 / 24 * 8192)))]  # +1 demi-ton, écrit pour ±24
    out = vst.to_messages(ev, {"bend_range": 2}, source_bend_range=24)
    assert abs(out[0].pitch - 4096) <= 8  # +1 demi-ton sur ±2 = la moitié de la course
    ev = [(0.0, mido.Message("pitchwheel", pitch=round(5 / 24 * 8192)))]  # +5 : au-delà de ±2, écrêté
    assert vst.to_messages(ev, {"bend_range": 2}, 24)[0].pitch == 8191


def test_module_volume_becomes_velocity():
    ev = [(0.0, mido.Message("control_change", control=11, value=64)), note(0.0, 60, 100), note(1.0, 62, 100)]
    out = vst.to_messages(ev, {}, 24)
    assert [m.type for m in out] == ["note_on", "note_on"]  # le CC 11 ne part pas au synthé
    assert out[0].velocity == 50 and out[1].time == 1.0
    kept = vst.to_messages(ev, {"expression": "cc11"}, 24)
    assert kept[0].type == "control_change" and kept[1].velocity == 100


def test_excerpt_restarts_at_zero_with_current_bend_and_volume():
    ev = [(0.0, mido.Message("control_change", control=11, value=90)),
          (1.0, mido.Message("pitchwheel", pitch=300)), note(2.0, 60), note(5.0, 64), note(9.0, 67)]
    part = excerpt(ev, start=4.0, length=4.0)
    assert sorted((t, m.type) for t, m in part) == [(0.0, "control_change"), (0.0, "pitchwheel"), (1.0, "note_on")]


def test_installed_finds_bundles_and_single_files(tmp_path, monkeypatch):
    a = tmp_path / "a"
    inner = a / "Synth.vst3" / "Contents" / "x86_64-win" / "Synth.vst3"
    inner.parent.mkdir(parents=True)
    inner.write_bytes(b"x")
    b = tmp_path / "b"
    b.mkdir()
    (b / "Drums.vst3").write_bytes(b"x")       # ancien format : un seul fichier
    (b / "Synth.vst3").write_bytes(b"x")       # même nom : celui du premier dossier gagne
    monkeypatch.setattr(vst, "DIRS", (a, b))
    found = vst.installed()
    assert set(found) == {"Synth", "Drums"}
    assert found["Synth"] == inner.resolve()
    assert vst.find("drums") == (b / "Drums.vst3").resolve()
    with pytest.raises(SystemExit):
        vst.find("Absent")


def test_catalogue_tries_each_plugin_once_and_keeps_crashes_aside(tmp_path, monkeypatch):
    (tmp_path / "Bad.vst3").write_bytes(b"x")
    (tmp_path / "Good.vst3").write_bytes(b"x")
    monkeypatch.setattr(vst, "DIRS", (tmp_path,))
    monkeypatch.setattr(vst, "TOOLS_VST", tmp_path)
    monkeypatch.setattr(vst, "CATALOGUE", tmp_path / "catalogue.json")
    tried = []

    def probe(path):
        tried.append(path.stem)
        return {"ok": False, "erreur": "plantage au chargement"} if path.stem == "Bad" else \
            {"ok": True, "instrument": True}
    monkeypatch.setattr(vst, "probe", probe)
    cat = vst.catalogue(log=lambda *_: None)
    assert cat["Good"]["ok"] and not cat["Bad"]["ok"]
    vst.catalogue(log=lambda *_: None)  # rien n'a changé : pas de nouvel essai
    assert sorted(tried) == ["Bad", "Good"]
    assert json.loads((tmp_path / "catalogue.json").read_text(encoding="utf-8"))["Bad"]["erreur"]


def test_state_change_invalidates_track_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(vst, "SONGS", tmp_path)
    (tmp_path / "s.bin").write_bytes(b"preset A")
    inst = midi.Instrument(vsti={"plugin": "Surge XT", "state": "s.bin"})
    ev = [note(0.0, 60)]
    k1 = render._part_key("p", ev, inst, 1.0, 0, "x.sf2")
    (tmp_path / "s.bin").write_bytes(b"preset B")
    assert render._part_key("p", ev, inst, 1.0, 0, "x.sf2") != k1


def test_no_vst_keeps_previous_cache_keys():
    """Sans VST, la clé d'une piste ne contient rien de nouveau : les pistes déjà rendues restent bonnes."""
    inst = midi.Instrument(sfz={"bank": "b", "program": "p"})
    import dataclasses, hashlib  # noqa: E401
    sound = dataclasses.asdict(inst)
    for k in ("name", "gain_db", "pan", "reverb", "share", "part", "fx", "by_channel", "double", "vsti", "humanize"):
        sound.pop(k, None)
    sound["heavy_fx"] = []
    h = hashlib.sha1(json.dumps([render.ENGINE_VERSION, "p", sound, 1.0, 0, "x.sf2", render.SR],
                                sort_keys=True, default=str).encode())
    h.update(f"{0.0:.6f}{note(0.0, 60)[1].hex()}".encode())
    assert render._part_key("p", [note(0.0, 60)], inst, 1.0, 0, "x.sf2") == h.hexdigest()


surge = pytest.mark.skipif("Surge XT" not in vst.installed(), reason="Surge XT absent (scripts/setup_tools.py)")


@surge
def test_surge_renders_a_track_and_its_state_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(vst, "SONGS", tmp_path)
    ev = [note(0.0, 60), (0.5, mido.Message("note_off", note=60)), note(0.6, 67), (1.0, mido.Message("note_off", note=67))]
    a = vst.render({"plugin": "Surge XT"}, ev, 2.0, 48000, source_bend_range=midi.BEND_RANGE)
    assert a.shape == (2, 96000)
    assert np.abs(a[:, :24000]).max() > 1e-3          # la note joue
    assert np.abs(a[:, -4800:]).max() < 1e-3          # puis se tait
    plug = vst.load("Surge XT")
    (tmp_path / "s.bin").write_bytes(plug.raw_state)
    b = vst.render({"plugin": "Surge XT", "state": "s.bin"}, ev, 2.0, 48000, source_bend_range=midi.BEND_RANGE)
    assert b.shape == a.shape and np.abs(b[:, :24000]).max() > 1e-3  # muet sans le passage à vide de prepare()


def test_juce_base64_round_trip():
    from remaster import vststate
    for data in (b"", b"a", b"sub3\x00\xff" * 37, bytes(range(256))):
        assert vststate.juce_b64decode(vststate.juce_b64encode(data)) == data
    assert vststate.juce_b64encode(b"\x01").startswith("1.")


def test_component_swapped_in_vst3_state():
    import struct
    from remaster import vststate
    xml = (f"<VST3PluginState><IComponent>{vststate.juce_b64encode(b'old patch')}</IComponent>"
           "<IEditController>3.AAA</IEditController></VST3PluginState>").encode()
    raw = b"VC2!" + struct.pack("<I", len(xml)) + xml + b"\0"
    assert vststate.split(raw)[0] == b"old patch"
    assert vststate.with_component(raw, b"old patch") == raw  # aller-retour à l'octet près
    new = vststate.with_component(raw, b"a new, longer patch")
    assert vststate.split(new)[0] == b"a new, longer patch" and b"<IEditController>3.AAA" in new


def test_fxp_chunk():
    import struct
    from remaster import vststate
    data = b"sub3" + b"\x07" * 20
    head = b"CcnK" + struct.pack(">I", 52 + len(data)) + b"FPCh" + struct.pack(">III", 1, 0x636A7333, 1) + \
        struct.pack(">I", 1) + b"Preset".ljust(28, b"\0") + struct.pack(">I", len(data))
    assert len(head) == 60
    assert vststate.fxp_chunk(head + data) == data
    with pytest.raises(ValueError):
        vststate.fxp_chunk(b"RIFF" + bytes(60))
