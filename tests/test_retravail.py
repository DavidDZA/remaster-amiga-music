"""Retouches du 21/11/2026 : accord général d'une musique, mélodie préférée dans une partie, octave d'un preset
compensée dans le VST, MP3 de l'original copié dans le dossier d'une musique retravaillée."""
from types import SimpleNamespace
import mido
import pytest
from remaster import analyze, score, vst, paths, render, modfile


def fake_song(notes):
    """notes : [(sample, demi-tons au-dessus du C-2)] ; une voie, une attaque par trame."""
    ticks = [SimpleNamespace(trigger=True, sample=s, note_period=modfile.C2_PERIOD * 2 ** (-x / 12))
             for s, x in notes]
    return SimpleNamespace(ticks=[ticks])


def test_tuning_offset_is_a_circular_mean(monkeypatch):
    roots = {1: 54.40, 2: 30.38, 4: 54.58}   # Giana : +40, +38 et +58 cents (ce dernier s'arrondit de l'autre côté)
    monkeypatch.setattr(analyze, "root_midi", lambda s: roots[s])
    mod = SimpleNamespace(samples={k - 1: k for k in roots})
    song = fake_song([(1, 0), (1, 2), (2, 5), (4, 0), (4, 7)])
    off = analyze.tuning_offset(mod, song)
    assert 40 < off < 50
    # sans l'accord, le sample 4 s'arrondit un demi-ton plus haut que les autres ; avec, tous du même côté
    assert round(54.58) - round(54.40) == 1
    assert round(54.58 - off / 100) == round(54.40 - off / 100) == 54
    # autour de ±50 cents, une moyenne simple se tromperait (−48 et +48 sont voisins) : pas la moyenne circulaire
    roots.update({1: 60.52, 2: 61.48})
    assert abs(abs(analyze.tuning_offset(mod, fake_song([(1, 0), (2, 0)]))) - 50) < 3


def test_tuning_cents_lowers_the_automatic_root(monkeypatch):
    monkeypatch.setattr(analyze, "root_midi", lambda s: 54.45)
    mod = SimpleNamespace(samples=[None])
    assert render.instrument({"samples": {"1": {}}}, mod, 1).root == pytest.approx(54.45)
    assert render.instrument({"tuning_cents": 45, "samples": {"1": {}}}, mod, 1).root == pytest.approx(54.0)
    assert render.instrument({"tuning_cents": 45, "samples": {"1": {"root": 50}}}, mod, 1).root == 50


def test_preferred_sample_is_the_melody_where_it_plays():
    bars = [(0, 4), (4, 4)]                     # deux mesures de 4 lignes
    arp = [score.Hit(r, r + 1, (80,), 6, 1) for r in range(8)]          # arpège aigu, voie 2, partout
    tune = [score.Hit(r, r + 2, (70,), 7, 2) for r in (4, 6)]           # mélodie, voie 3, mesure 2 seulement
    parts = {"Mélodie": {"samples": [6, 7], "lead": True, "prefer": [7]}}
    got = score.assign(arp + tune, parts, bars)["Mélodie"]
    assert {h.sample for h in got if h.row < 4} == {6}   # mesure 1 : la mélodie se tait, l'arpège la remplace
    assert {h.sample for h in got if h.row >= 4} == {7}  # mesure 2 : la vraie mélodie, même plus grave
    old = score.assign(arp + tune, {"Mélodie": {"samples": [6, 7], "lead": True}}, bars)["Mélodie"]
    assert {h.sample for h in old} == {6}                # avant : toujours la voie la plus aiguë


def test_preset_octave_is_compensated_inside_the_vst_only():
    ev = [(0.0, mido.Message("note_on", note=48, velocity=100)), (0.5, mido.Message("note_off", note=48))]
    out = vst.to_messages(ev, {"transpose": 12}, 24)
    assert [m.note for m in out] == [60, 60]
    inst = render.instrument({"samples": {"1": {"root": 40, "vsti": {"plugin": "x", "transpose": 12}}}},
                             SimpleNamespace(samples=[None]), 1)
    assert inst.transpose == 0  # la partition et le piano gardent les notes de la musique


def test_original_mp3_copied_into_the_work_folder(tmp_path, monkeypatch):
    orig = tmp_path / "Originaux" / "Strider"
    orig.mkdir(parents=True)
    (orig / "Strider - Strider [Custom Version] (5) (original).mp3").write_bytes(b"mp3")
    monkeypatch.setattr(paths, "ORIGINALS", tmp_path / "Originaux")
    work = tmp_path / "Retravaillées" / "Strider - Strider [Custom Version] (5)"
    got = paths.copy_original(work)
    assert got.read_bytes() == b"mp3" and got.parent == work
    assert paths.copy_original(tmp_path / "Retravaillées" / "Inconnue") is None
