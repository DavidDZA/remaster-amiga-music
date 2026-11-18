"""Télécharge libxmp (bibliothèque libre de lecture de modules, licence MIT) et la compile en DLL dans tools\\libxmp\\bin.

    .venv\\Scripts\\python scripts\\build_libxmp.py

Il faut un compilateur C MinGW 64 bits : celui de MSYS2 (C:\\msys64\\mingw64\\bin\\gcc.exe) est utilisé s'il est là,
sinon un gcc trouvé dans le PATH. La DLL sert à remaster/xmpconv.py (conversion d'autres formats en .mod).
"""
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
VERSION = "4.6.3"
URL = f"https://github.com/libxmp/libxmp/releases/download/libxmp-{VERSION}/libxmp-{VERSION}.tar.gz"
DEST = ROOT / "tools" / "libxmp"


def gcc() -> str:
    for p in (pathlib.Path(r"C:\msys64\mingw64\bin\gcc.exe"), shutil.which("gcc")):
        if p and pathlib.Path(p).exists():
            return str(p)
    sys.exit("Pas de compilateur gcc (MinGW 64 bits) : installer MSYS2, ou mettre gcc dans le PATH.")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    dll = DEST / "bin" / "libxmp.dll"
    if dll.exists():
        print("déjà là :", dll)
        return
    DEST.mkdir(parents=True, exist_ok=True)
    src = DEST / f"libxmp-{VERSION}"
    if not src.exists():
        archive = DEST / f"libxmp-{VERSION}.tar.gz"
        print("téléchargement :", URL)
        with urllib.request.urlopen(URL) as r, open(archive, "wb") as f:
            shutil.copyfileobj(r, f)
        with tarfile.open(archive) as t:
            t.extractall(DEST, filter="data")
    # la liste des sources est celle du Makefile Visual C++ ; sans la version « lite » ni les tests
    names = re.findall(r"[A-Za-z0-9_./\\-]+\.obj", (src / "Makefile.vc").read_text(encoding="latin-1"))
    sources = sorted({n.replace("\\", "/")[:-4] + ".c" for n in names})
    sources = [s for s in sources if (src / s).exists() and "lite" not in s and not s.startswith("test/")]
    (DEST / "bin").mkdir(exist_ok=True)
    print(f"compilation de {len(sources)} fichiers…")
    r = subprocess.run([gcc(), "-O2", "-shared", "-DBUILDING_DLL", "-Iinclude", "-Isrc", "-static-libgcc",
                        "-o", str(dll), *sources], cwd=src, capture_output=True, text=True)
    if r.returncode != 0 or not dll.exists():
        sys.exit("échec de la compilation :\n" + r.stderr[-3000:])
    print("→", dll)


if __name__ == "__main__":
    main()
