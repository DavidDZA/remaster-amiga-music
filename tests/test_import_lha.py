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
