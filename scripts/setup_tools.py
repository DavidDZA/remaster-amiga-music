"""Télécharge les outils gratuits dans tools/ (ignoré par git). Relancer sans risque : ce qui est déjà là est gardé."""
import pathlib, urllib.request, zipfile, shutil, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"

DOWNLOADS = [
    # (dossier, fichier, adresse)  -- versions figées pour des rendus reproductibles
    ("fluidsynth", "fluidsynth.zip",
     "https://github.com/FluidSynth/fluidsynth/releases/download/v2.6.2/fluidsynth-v2.6.2-win10-x64-cpp11.zip"),
    ("openmpt", "openmpt.zip",
     "https://lib.openmpt.org/files/libopenmpt/bin/libopenmpt-0.8.10+release.bin.windows.zip"),
    ("soundfonts", "GeneralUser-GS.sf2",
     "https://raw.githubusercontent.com/mrbumpy409/GeneralUser-GS/main/GeneralUser-GS.sf2"),
    ("soundfonts", "MuseScore_General.sf3",
     "https://ftp.osuosl.org/pub/musescore/soundfont/MuseScore_General/MuseScore_General.sf3"),
]

def main():
    for folder, name, url in DOWNLOADS:
        dest_dir = TOOLS / folder
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / name
        if dest.suffix == ".zip":
            if any(p.suffix == ".exe" for p in dest_dir.rglob("*.exe")):
                print("déjà là :", folder); continue
        elif dest.exists():
            print("déjà là :", name); continue
        print("téléchargement :", url)
        tmp = dest.with_suffix(dest.suffix + ".part")
        with urllib.request.urlopen(url) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        tmp.rename(dest)
        if dest.suffix == ".zip":
            with zipfile.ZipFile(dest) as z:
                for m in z.namelist():  # pas de chemins qui sortent du dossier
                    if m.startswith(("/", "\\")) or ".." in pathlib.PurePath(m).parts:
                        sys.exit(f"archive suspecte : {m}")
                z.extractall(dest_dir)
            dest.unlink()
    print("ok")

if __name__ == "__main__":
    main()
