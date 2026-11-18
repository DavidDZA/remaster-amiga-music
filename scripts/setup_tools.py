"""Télécharge les outils gratuits dans tools/ (ignoré par git). Relancer sans risque : ce qui est déjà là est gardé."""
import pathlib, urllib.request, zipfile, tarfile, shutil, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"

DOWNLOADS = [
    # (dossier, fichier, adresse)  -- versions figées pour des rendus reproductibles
    ("fluidsynth", "fluidsynth.zip",
     "https://github.com/FluidSynth/fluidsynth/releases/download/v2.6.2/fluidsynth-v2.6.2-win10-x64-cpp11.zip"),
    ("openmpt", "openmpt.zip",
     "https://lib.openmpt.org/files/libopenmpt/bin/libopenmpt-0.8.10+release.bin.windows.zip"),
    ("dragonfly", "dragonfly.zip",  # réverbérations open source (GPL), en VST3
     "https://github.com/michaelwillis/dragonfly-reverb/releases/download/3.2.10/dragonfly-reverb-3.2.10-win64.zip"),
    ("soundfonts", "GeneralUser-GS.sf2",
     "https://raw.githubusercontent.com/mrbumpy409/GeneralUser-GS/main/GeneralUser-GS.sf2"),
    ("soundfonts", "MuseScore_General.sf3",
     "https://ftp.osuosl.org/pub/musescore/soundfont/MuseScore_General/MuseScore_General.sf3"),
    ("lilypond", "lilypond.zip",  # gravure des partitions et tablatures (GPL)
     "https://gitlab.com/lilypond/lilypond/-/releases/v2.24.4/downloads/lilypond-2.24.4-mingw-x86_64.zip"),
    ("piano", "salamander.tar.xz",  # Salamander Grand Piano V3, Yamaha C5, en SF2 (CC-BY 3.0, Alexander Holm) : 310 Mo
     "https://freepats.zenvoid.org/Piano/SalamanderGrandPiano/SalamanderGrandPiano-SF2-V3+20200602.tar.xz"),
]

ARCHIVES = (".zip", ".xz")

def main():
    for folder, name, url in DOWNLOADS:
        dest_dir = TOOLS / folder
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / name
        if dest.suffix in ARCHIVES:
            if any(f.is_file() and not f.name.endswith(".part") for f in dest_dir.rglob("*")):
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
        elif dest.suffix == ".xz":
            with tarfile.open(dest) as t:
                t.extractall(dest_dir, filter="data")  # refuse les chemins qui sortent du dossier
            dest.unlink()
    print("ok")

if __name__ == "__main__":
    main()
