"""Grave les partitions en images (PNG) pour les relire page par page avant de les donner.

    .venv\\Scripts\\python scripts\\preview_pages.py "out\\Retravaillées\\Dr Mario\\partitions"

Les images vont dans <dossier>\\apercu\\ (une par page). C'est ainsi que Claude vérifie la gravure : il ne peut pas
ouvrir un PDF page par page, mais il peut regarder une image.
"""
import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from remaster import lily  # noqa: E402


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    src = pathlib.Path(sys.argv[1])
    dest = src / "apercu"
    dest.mkdir(exist_ok=True)
    for ly in sorted(src.glob("*.ly")):
        copy = dest / ly.name
        shutil.copyfile(ly, copy)
        pages = lily.compile_png(copy, resolution=90)
        copy.unlink()
        print(f"{ly.stem} : {len(pages)} page(s)")
    print(f"→ {dest}")


if __name__ == "__main__":
    main()
