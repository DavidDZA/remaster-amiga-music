"""Arrangements pour piano de plusieurs musiques d'un coup (une liste « fichier » ou « fichier | n° de morceau »).

    .venv\\Scripts\\python scripts\\piano_batch.py liste.txt

Chaque ligne de la liste : le chemin de la musique dans in\\music, et pour un format autre que .mod le n° du
sous-morceau après « | » (le même que dans le nom du MP3). Les lignes vides ou commençant par # sont ignorées.
Une fiche automatique est créée pour chaque musique qui n'en a pas (remaster/roles.py).
"""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    lines = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
    py = ROOT / ".venv" / "Scripts" / "python.exe"
    ok, failed = [], []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        path, _, number = (x.strip() for x in line.partition("|"))
        cmd = [str(py), "-m", "remaster.piano", path] + (["--sous-morceau", number] if number else [])
        print(f"=== {path}" + (f" ({number})" if number else ""), flush=True)
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = [x for x in r.stdout.splitlines() if not x.startswith("DPF")]
        print("\n".join(out), flush=True)
        if r.returncode:
            print(r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "erreur", flush=True)
            failed.append(line)
        else:
            ok.append(line)
    print(f"\n{len(ok)} réussis, {len(failed)} en échec" + (f" : {failed}" if failed else ""))


if __name__ == "__main__":
    main()
