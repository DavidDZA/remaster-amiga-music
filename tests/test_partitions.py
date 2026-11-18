"""Tablatures, batterie et arrangement pour piano (Dr Mario)."""
import pathlib
import re
import pytest
from remaster import lily, fretboard, score, partitions, piano, render

ROOT = pathlib.Path(__file__).resolve().parent.parent
MOD = ROOT / "in" / "mod" / "Dr Mario" / "Dr Mario.mod"
CFG = render.load_config(ROOT / "songs" / "Dr Mario.json")
ROWS = {"16": 1, "8": 2, "8.": 3, "4": 4, "4.": 6, "2": 8, "2.": 12, "1": 16}


@pytest.fixture(scope="module")
def ctx():
    return partitions.Context(MOD, CFG)


@pytest.fixture(scope="module")
def parts(ctx):
    return score.assign(ctx.hits + ctx.extras, CFG["partitions"], ctx.bars)


def bar_rows(txt: str) -> int:
    """Durée d'une mesure écrite (en lignes du module)."""
    txt = re.sub(r"<[^>]*>", "x", txt)
    total = 0
    for tok in txt.split():
        m = re.match(r"^[a-zRrs][a-z,']*?(16|8\.|8|4\.|4|2\.|2|1)(\*\d+)?", tok)
        if m:
            total += ROWS[m.group(1)] * (int(m.group(2)[1:]) if m.group(2) else 1)
    return total


def test_decoupage_des_durees():
    assert lily.split(0, 16) == [16]
    assert lily.split(0, 6) == [6]
    assert lily.split(2, 4) == [2, 2]          # une noire à cheval sur le temps : deux croches liées
    assert lily.split(1, 3) == [3]             # croche pointée qui finit sur le temps
    assert lily.split(14, 4, 16) == [2]        # coupée à la barre de mesure
    assert sum(lily.split(5, 9)) == 9


def test_noms_de_notes():
    assert lily.pitch(60) == "c'"
    assert lily.pitch(40) == "e,"
    assert lily.pitch(70) == "ais'" and lily.pitch(70, flats=True) == "bes'"


def test_mesure_complete():
    txt = lily.bar_music(16, [(2, 4, "e", ""), (10, 3, "<e b>", "")])
    assert bar_rows(txt) == 16
    assert "~" in txt  # la note de 4 lignes qui démarre en 2 est liée


def test_power_chord_sur_le_manche():
    f, lost = fretboard.assign([(40, 47, 52)])
    assert lost == 0
    assert sorted((s, fr) for _p, s, fr in f[0]) == [(4, 2), (5, 2), (6, 0)]  # mi ouvert : 0-2-2


def test_cordes_voisines_et_doigts():
    fings, _ = fretboard.assign([(52, 59), (50, 57, 62), (47, 54, 59)])
    for f in fings:
        strings = sorted(s for _p, s, _fr in f)
        assert strings == list(range(strings[0], strings[0] + len(strings)))  # pas de corde sautée
        used = [fr for _p, _s, fr in f if fr]
        assert not used or max(used) - min(used) <= 4


def test_accord_injouable_reduit():
    f, lost = fretboard.assign([(40, 47, 52, 55, 59, 62, 64, 67)])
    assert lost >= 2 and len(f[0]) <= 6


def test_grille_du_morceau(ctx):
    assert len(ctx.bars) == 216 and all(n == 16 for _s, n in ctx.bars)
    assert set(ctx.tempi) == {150, 125, 107}
    assert ctx.sections[0][0] == "A"
    assert ctx.key == (4, True)  # mi mineur


def test_parties(ctx, parts):
    lead = score.events(parts["Guitare 1 (lead)"])
    assert lead and all(len(e.pitches) == 1 for e in lead)  # une seule ligne de lead
    drums = parts["Batterie (version enrichie)"]
    notes = {h.pitches[0] for h in drums}
    assert {36, 38, 42, 49} <= notes  # grosse caisse, caisse claire + charleston et crashs ajoutés
    assert sum(1 for h in drums if h.pitches[0] == 49) == len(ctx.extras) - sum(
        1 for h in ctx.extras if h.pitches[0] == 42)
    bass = score.events(parts["Basse"])
    score.fit_range(bass, fretboard.BASS[0])
    assert min(min(e.pitches) for e in bass) >= 28


def test_bends():
    e = score.Event(0, 6, (64,), bend=[0, 0, 1, 1, 0, 0])
    assert [t for _r, t in score.bend_marks(e)] == ["b. ½", "lâcher"]
    e = score.Event(0, 4, (64,), bend=[0, 2, 2, 2])
    assert [t for _r, t in score.bend_marks(e)] == ["b. 1"]
    e = score.Event(0, 6, (52, 59), bend=[0, -1, 0, -1, 0, -1])
    assert [t for _r, t in score.bend_marks(e)] == ["vibr."]


def test_mesures_ecrites_completes(ctx, parts):
    text, _stats, _used = partitions.fretted_part(ctx, "G2", parts["Guitare 2 (rythmique)"], "guitare")
    music = re.search(r"music = \{\n  \\compressEmptyMeasures\n(.*?)\n\}", text, re.S).group(1)
    assert sum(bar_rows(line) for line in music.splitlines()) == 216 * 16


def test_arrangement_piano(ctx):
    arr = piano.arrange(ctx, CFG)
    assert len(arr.melody) > 200 and len(arr.left) > 500
    assert all(min(n.pitches) >= 55 for n in arr.melody)  # main droite : sol 3 au plus grave
    assert all(max(n.pitches) <= 59 for n in arr.left)          # main gauche sous le do du milieu
    for c in arr.chords:
        assert len(c.pitches) == 3 and c.pitches[-1] - c.pitches[0] <= 12
        over = [m for m in arr.melody if m.row < c.end and m.end > c.row]
        assert all(max(c.pitches) < min(m.pitches) for m in over)  # accords sous la mélodie
    ev = piano.to_midi(ctx, arr)
    assert max(t for t, _m in ev) <= ctx.song.duration + 0.1


def test_tierce_choisie():
    em = (4, True)
    assert piano.third_of(4, em, []) == 7       # mi mineur : sol
    assert piano.third_of(0, em, []) == 4       # do majeur dans mi mineur : mi
    assert piano.third_of(11, em, [3, 3]) == 3  # la mélodie chante ré# : si majeur


@pytest.mark.skipif(not list((ROOT / "tools").glob("lilypond/*/bin/lilypond.exe")), reason="LilyPond absent")
def test_gravure(ctx, parts, tmp_path):
    text, _ = partitions.drum_part(ctx, parts["Batterie (version enrichie)"])
    ly = tmp_path / "batterie.ly"
    ly.write_text(lily.header("Test", "Batterie", "") + text, encoding="utf-8")
    assert lily.compile_pdf(ly).stat().st_size > 10_000
