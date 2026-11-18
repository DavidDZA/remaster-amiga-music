"""Récupère les modules ProTracker des archives de musiques de jeux Amiga (.lha) et les range par jeu.

    .venv\\Scripts\\python scripts\\import_lha.py            # toutes les archives de in\\lha\\
    .venv\\Scripts\\python scripts\\import_lha.py --essai    # dire ce qui serait fait, sans rien écrire

Les archives (format « UnExoticA ») nomment chaque musique par un préfixe qui donne son format : `mod.` = ProTracker
(ce que lit Remaster AMIGA Music), `med.` = OctaMED, `mdat.` = TFMX, `dw.` = David Whittaker, `cust.` = lecteur
propre au jeu… Seuls les `mod.` (ou `*.mod`) sont repris, et seulement s'ils se lisent vraiment (signature M.K.,
FLT4… et 31 samples) : les autres formats sont listés à la fin.

Rangement : in\\mod\\<Jeu>\\<Jeu>.mod s'il n'y a qu'une musique, sinon in\\mod\\<Jeu>\\<Jeu> - <titre>.mod
(le nom du fichier sert aussi à la fiche songs\\<nom>.json et au dossier out\\<nom>\\ : il doit être unique).
Un module déjà présent (mêmes octets) n'est pas recopié.

Lecture : 7-Zip (tools\\7zip\\7z.exe, sinon celui installé dans Program Files), fichier par fichier, sans extraction
sur le disque. Les modules Soundtracker à 15 samples (sans signature) sont acceptés aussi.
"""
from __future__ import annotations
import argparse
import collections
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from remaster import modfile, player  # noqa: E402

FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def seven_zip() -> pathlib.Path:
    for p in [ROOT / "tools" / "7zip" / "7z.exe",
              pathlib.Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "7-Zip" / "7z.exe",
              pathlib.Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "7-Zip" / "7z.exe"]:
        if p.exists():
            return p
    raise SystemExit("7-Zip introuvable : le mettre dans tools\\7zip\\ (7z.exe et 7z.dll) ou l'installer.")


def entries(z: pathlib.Path, archive: pathlib.Path) -> list[str]:
    """Chemins des fichiers de l'archive (sans les dossiers)."""
    out = subprocess.run([str(z), "l", "-slt", "-ba", str(archive)], capture_output=True, text=True,
                         encoding="utf-8", errors="replace").stdout
    files, path, folder = [], None, False
    for line in out.splitlines() + [""]:
        if line.startswith("Path = "):
            path = line[7:]
        elif line.startswith("Folder = "):
            folder = line[9:].strip() == "+"
        elif not line.strip() and path is not None:
            if not folder:
                files.append(path)
            path, folder = None, False
    return files


def music_kind(path: str) -> str:
    """Format d'après le nom : « mod.titre » → mod ; « titre.mod » → mod ; sinon le préfixe."""
    name = path.replace("\\", "/").split("/")[-1]
    if name.lower().endswith(".mod"):
        return "mod"
    return name.split(".", 1)[0].lower() if "." in name else "?"


def title_of(path: str) -> str:
    name = path.replace("\\", "/").split("/")[-1]
    if name.lower().startswith("mod."):
        name = name[4:]
    elif name.lower().endswith(".mod"):
        name = name[:-4]
    return clean(name)


def clean(s: str) -> str:
    s = FORBIDDEN.sub("_", s).strip(" .")
    return s or "sans nom"


def game_of(archive: pathlib.Path) -> str:
    return clean(archive.stem.replace("_", " "))


def readable(data: bytes) -> str | None:
    """None si c'est un module ProTracker que le projet sait lire, sinon la raison."""
    if len(data) < 1084:
        return "trop court"
    tag = data[1080:1084]
    if tag not in modfile.CHANNEL_TAGS and not modfile.is_soundtracker(data):
        return "ni ProTracker (signature M.K.…), ni Soundtracker 15 samples"
    try:
        with tempfile.NamedTemporaryFile(suffix=".mod", delete=False) as f:
            f.write(data)
        mod = modfile.load(pathlib.Path(f.name))
        if not mod.orders:
            return "aucun pattern"
        song = player.play(mod)  # il doit vraiment se jouer avec le lecteur du projet
        notes = sum(tk.trigger for ch in song.ticks for tk in ch)
        if song.duration < 2 or notes < 8:
            return f"ne se joue pas ({song.duration:.1f} s, {notes} notes)"
    except Exception as e:  # noqa: BLE001 — un fichier abîmé ne doit pas arrêter l'import
        return f"illisible ({e})"
    finally:
        os.unlink(f.name)
    return None


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Range les .mod des archives .lha de in\\lha dans in\\mod\\<jeu>\\.")
    ap.add_argument("--lha", type=pathlib.Path, default=ROOT / "in" / "lha")
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "in" / "mod")
    ap.add_argument("--essai", action="store_true", help="ne rien écrire")
    a = ap.parse_args()
    z = seven_zip()
    added, same, refused = [], [], []
    other: dict[str, collections.Counter] = {}
    for archive in sorted(a.lha.glob("*.lha")) + sorted(a.lha.glob("*.lzh")):
        files = entries(z, archive)
        mods = [f for f in files if music_kind(f) == "mod"]
        kinds = collections.Counter(music_kind(f) for f in files if music_kind(f) != "mod")
        if kinds:
            other[archive.name] = kinds
        if not mods:
            continue
        game = game_of(archive)
        ok = []
        for m in mods:
            # lu directement depuis l'archive (sortie standard) : rien n'est écrit avant contrôle, et les noms
            # interdits sous Windows (« game continue ... ») ne posent pas de problème
            r = subprocess.run([str(z), "e", "-so", str(archive), m], capture_output=True)
            data = r.stdout
            if r.returncode != 0 or not data:
                refused.append((archive.name, m, "lecture impossible dans l'archive"))
                continue
            why = readable(data)
            if why:
                refused.append((archive.name, m, why))
            else:
                ok.append((m, data))
        titles = collections.Counter(title_of(m) for m, _ in ok)
        if True:
            for m, data in ok:
                t = title_of(m)
                name = game if len(ok) == 1 else f"{game} - {t}"
                if titles[t] > 1:  # deux titres identiques dans le même jeu
                    name += f" ({ok.index((m, data)) + 1})"
                dest_dir = a.out / game
                dest = dest_dir / f"{name}.mod"
                existing = [p for p in dest_dir.glob("*.mod")] if dest_dir.exists() else []
                if any(p.read_bytes() == data for p in existing):
                    same.append(dest)
                    continue
                if dest.exists():  # même nom, contenu différent : on ne remplace pas
                    dest = dest_dir / f"{name} - {t}.mod"
                added.append(dest)
                if not a.essai:
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(data)
    verb = "à ajouter" if a.essai else "ajoutés"
    print(f"{len(added)} modules {verb}, {len(same)} déjà présents, {len(refused)} refusés")
    by_game = collections.Counter(p.parent.name for p in added)
    for g, n in sorted(by_game.items()):
        print(f"  {g} : {n}")
    if refused:
        print("\nrefusés :")
        for arch, m, why in refused:
            print(f"  {arch} : {m} — {why}")
    if other:
        total = collections.Counter()
        for k in other.values():
            total.update(k)
        print("\nautres formats, pas encore lus par le projet (fichiers) : "
              + ", ".join(f"{k} {n}" for k, n in total.most_common()))
        no_mod = [n for n, k in other.items() if n not in {r[0] for r in refused}
                  and not any(p.parent.name == game_of(pathlib.Path(n)) for p in added + same)]
        print(f"archives sans aucun .mod ({len(no_mod)}) : " + ", ".join(pathlib.Path(n).stem for n in no_mod))


if __name__ == "__main__":
    main()
