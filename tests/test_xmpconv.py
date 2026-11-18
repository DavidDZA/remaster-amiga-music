"""Conversion d'autres formats en .mod avec libxmp (remaster/xmpconv.py)."""
import pathlib
import pytest
from remaster import xmpconv, modfile, player

ROOT = pathlib.Path(__file__).resolve().parent.parent
MOD = ROOT / "in" / "music" / "Dr Mario" / "Dr Mario.mod"
needs_dll = pytest.mark.skipif(not xmpconv.DLL.exists(), reason="libxmp absente (scripts/build_libxmp.py)")


def test_periodes_protracker():
    assert xmpconv.period_of(xmpconv.NOTE_C2) == 428       # C-2
    assert xmpconv.period_of(xmpconv.NOTE_C2 - 12) == 856  # C-1
    assert xmpconv.period_of(xmpconv.NOTE_C2 + 23) == 113  # B-3
    assert xmpconv.period_of(xmpconv.NOTE_C2 + 24) == 107  # C-4 : hors table, la moitié de C-3 (214)


def test_tempo_protracker():
    assert xmpconv._pt_tempo(6, 2.5 / 125) == (6, 125)
    s, b = xmpconv._pt_tempo(6, 0.1)                       # tick trop long pour un BPM ProTracker
    assert abs(s * 2.5 / b - 0.6) < 0.01


@needs_dll
def test_aller_retour_dr_mario(tmp_path):
    data, rep = xmpconv.to_mod(MOD, title="friend or fom")
    assert rep["voies"] == 4 and not rep["pertes"]
    out = tmp_path / "rt.mod"
    out.write_bytes(data)
    a, b = modfile.load(MOD), modfile.load(out)
    assert a.orders == b.orders
    notes = lambda m: [(n.period, n.sample) for p in m.patterns for r in p for n in r]  # noqa: E731
    assert notes(a) == notes(b)
    assert all(x.data.tobytes() == y.data.tobytes() for x, y in zip(a.samples, b.samples))
    assert abs(player.play(b).duration - player.play(a).duration) < 0.5


@needs_dll
def test_fichier_inconnu(tmp_path):
    f = tmp_path / "rien.bin"
    f.write_bytes(b"pas une musique" * 100)
    with pytest.raises(ValueError):
        xmpconv.to_mod(f)
