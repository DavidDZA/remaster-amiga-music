"""Noms et formats lors de l'import des archives .lha (scripts/import_lha.py)."""
import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("import_lha", ROOT / "scripts" / "import_lha.py")
imp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(imp)


def test_format_d_apres_le_nom():
    assert imp.music_kind(r"Dr_Mario\mod.friend or fom") == "mod"
    assert imp.music_kind(r"Jeu\Musique.MOD") == "mod"
    assert imp.music_kind(r"Cannon_Fodder\rjp.JON") == "rjp"
    assert imp.music_kind(r"Batman\Custom_Versions\cust.cave") == "cust"


def test_noms_de_fichiers_windows():
    assert imp.title_of(r"Leander\mod.game continue ...") == "game continue"
    assert imp.title_of(r"X\mod.a:b?c") == "a_b_c"
    assert imp.game_of(pathlib.Path("Shadow_of_the_Beast_2.lha")) == "Shadow of the Beast 2"


def test_module_lisible():
    data = (ROOT / "in" / "music" / "Dr Mario" / "Dr Mario.mod").read_bytes()
    assert imp.readable(data) is None
    assert imp.readable(b"\0" * 2000) is not None


def test_versions_alternatives(tmp_path):
    o = tmp_path / "Batman" / "originaux"
    (o / "Custom_Versions").mkdir(parents=True)
    for f in (o / "jd.cave", o / "Custom_Versions" / "cust.cave", o / "smp.cave", o / "jd.title"):
        f.write_bytes(b"x")
    assert imp.uade_title(o / "jd.cave") == "cave"
    assert imp.uade_title(o / "Custom_Versions" / "cust.cave") == "cave [Custom Versions]"
    assert imp.uade_title(o / "jd.title") == "title"   # pas de doublon : pas de crochets


def test_rangement_par_jeu():
    from remaster import paths
    dm = ROOT / "in" / "music" / "Dr Mario" / "Dr Mario.mod"
    assert paths.game_of(dm) == "Dr Mario"
    assert paths.game_of(ROOT / "in" / "music" / "Turrican 3" / "originaux" / "mdat.world_1") == "Turrican 3"
    assert paths.game_dir(dm) == ROOT / "out" / "Dr Mario"
    assert paths.work_dir(dm) == ROOT / "out" / "Dr Mario" / "Dr Mario"
    assert paths.work_dir(dm, "Turrican 3 - world_1 (2)").name == "Turrican 3 - world_1 (2)"
