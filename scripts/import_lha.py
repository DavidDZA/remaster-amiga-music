"""Récupère toute la musique des archives de jeux Amiga (.lha) et la range par jeu dans in\\music\\<Jeu>\\.

    .venv\\Scripts\\python scripts\\import_lha.py            # toutes les archives de in\\lha\\
    .venv\\Scripts\\python scripts\\import_lha.py --essai    # dire ce qui serait fait, sans rien écrire

Les archives (format « UnExoticA ») nomment chaque fichier par un préfixe qui donne son format : `mod.` ProTracker,
`med.` OctaMED, `p4x.` The Player 4, `sfx.` SoundFX, `gmc.` Game Music Creator, `di.` Digital Illusions,
`mdat.` TFMX, `dw.` David Whittaker, `rjp.` Richard Joseph, `cust.` lecteur propre au jeu… et `smp.`, `smpl.` pour
les samples qui vont avec.

Pour chaque jeu, dans in\\music\\<Jeu>\\ :
- **les musiques en .mod**, que lit Remaster AMIGA Music : le fichier d'origine s'il est déjà en ProTracker ou
  Soundtracker, sinon **converti** avec libxmp (remaster/xmpconv.py) quand libxmp sait le lire. Chaque .mod est
  vérifié : il se joue avec le lecteur du projet et dure comme chez libxmp (à 10 % près) ;
  nom : <Jeu>.mod s'il n'y a qu'une musique, sinon <Jeu> - <titre>.mod (unique : il sert pour songs\\ et out\\) ;
- **originaux\\** : tous les fichiers de l'archive, tels quels, quel que soit le format (rien n'est perdu ;
  les formats pas encore lus pourront l'être plus tard) ;
et in\\music\\INVENTAIRE.md : ce qui est lisible, converti, pas encore lu, abîmé.

Lecture : 7-Zip (tools\\7zip\\7z.exe, sinon celui installé dans Program Files), fichier par fichier, directement
dans l'archive (rien n'est écrit avant contrôle ; les noms interdits sous Windows, « game continue ... », passent).
"""
from __future__ import annotations
import argparse
import collections
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from remaster import modfile, player  # noqa: E402

FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
COMPANIONS = {"smp", "smpl", "ins", "8svx", "sfx_smp"}   # samples qui accompagnent une musique
NAMES = {"mod": "ProTracker", "med": "OctaMED", "p4x": "The Player 4", "sfx": "SoundFX", "gmc": "Game Music Creator",
         "di": "Digital Illusions", "xm": "FastTracker 2", "mdat": "TFMX (Chris Hülsbeck)",
         "dw": "David Whittaker", "rjp": "Richard Joseph", "cust": "lecteur propre au jeu", "bd": "Ben Daglish",
         "dl": "Dave Lowe", "bss": "Beathoven Synthesizer"}  # les autres préfixes sont affichés tels quels


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
    low = name.lower()
    if low.endswith(".mod"):
        name = name[:-4]
    elif "." in name:
        name = name.split(".", 1)[1]
    return clean(name)


def clean(s: str) -> str:
    s = FORBIDDEN.sub("_", s).strip(" .")
    return s or "sans nom"


def game_of(archive: pathlib.Path) -> str:
    return clean(archive.stem.replace("_", " "))


def plays(data: bytes) -> str | None:
    """None si ce .mod se lit et se joue avec le lecteur du projet, sinon la raison."""
    if len(data) < 1084:
        return "trop court"
    if data[1080:1084] not in modfile.CHANNEL_TAGS and not modfile.is_soundtracker(data) \
            and not (data[1082:1084] == b"CH" and data[1080:1082].isdigit()):
        return "ni ProTracker, ni Soundtracker"
    with tempfile.NamedTemporaryFile(suffix=".mod", delete=False) as f:
        f.write(data)
    try:
        mod = modfile.load(pathlib.Path(f.name))
        song = player.play(mod)
        notes = sum(tk.trigger for ch in song.ticks for tk in ch)
        if song.duration < 2 or notes < 8:
            return f"ne se joue pas ({song.duration:.1f} s, {notes} notes)"
    except Exception as e:  # noqa: BLE001 — un fichier abîmé ne doit pas arrêter l'import
        return f"illisible ({e})"
    finally:
        os.unlink(f.name)
    return None


readable = plays  # ancien nom


def convert(data: bytes, title: str) -> tuple[bytes | None, str]:
    """(.mod converti, format d'origine) avec libxmp, ou (None, raison)."""
    from remaster import xmpconv
    with tempfile.TemporaryDirectory() as tmp:
        src = pathlib.Path(tmp, "musique")
        src.write_bytes(data)
        try:
            out, rep = xmpconv.to_mod(src, title=title)
        except (ValueError, OSError) as e:
            return None, str(e)
    why = plays(out)
    if why:
        return None, f"converti mais {why}"
    with tempfile.NamedTemporaryFile(suffix=".mod", delete=False) as f:
        f.write(out)
    try:
        dur = player.play(modfile.load(pathlib.Path(f.name))).duration
    finally:
        os.unlink(f.name)
    ref = rep["durée_libxmp"]
    if ref and not 0.9 < dur / ref < 1.1:
        return None, f"converti mais durée {dur:.0f} s au lieu de {ref:.0f} s"
    return out, rep["format"]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Range la musique des archives .lha de in\\lha dans in\\music\\<jeu>\\.")
    ap.add_argument("--lha", type=pathlib.Path, default=ROOT / "in" / "lha")
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "in" / "music")
    ap.add_argument("--essai", action="store_true", help="ne rien écrire")
    a = ap.parse_args()
    z = seven_zip()
    inventory = []
    totals = collections.Counter()
    for archive in sorted(a.lha.glob("*.lha")) + sorted(a.lha.glob("*.lzh")):
        game = game_of(archive)
        gdir = a.out / game
        files = entries(z, archive)
        got: list[tuple[str, bytes]] = []
        damaged = []
        for path in files:
            r = subprocess.run([str(z), "e", "-so", str(archive), path], capture_output=True)
            if r.returncode != 0:
                damaged.append(path)
            if r.stdout:
                got.append((path, r.stdout))
        # 1. originaux, tels quels
        if not a.essai:
            for path, data in got:
                parts = [clean(p) for p in path.replace("\\", "/").split("/")]
                if len(parts) > 1 and parts[0].replace("_", " ") == game:
                    parts = parts[1:]  # le dossier du jeu, déjà dans le chemin
                dest = gdir / "originaux" / pathlib.Path(*parts)
                if not dest.exists() or dest.read_bytes() != data:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(data)
        # 2. musiques lisibles en .mod
        candidates = [(p, d) for p, d in got if music_kind(p) not in COMPANIONS and music_kind(p) != "?"
                      and p not in damaged]
        mods, not_read = [], collections.Counter()
        for path, data in candidates:
            kind = music_kind(path)
            if kind == "mod" and plays(data) is None:
                mods.append((path, data, "d'origine"))
                continue
            out, how = convert(data, title_of(path))
            if out is None:
                not_read[kind] += 1
            else:
                mods.append((path, out, f"converti ({how})"))
        titles = collections.Counter(title_of(p) for p, _, _ in mods)
        seen = collections.Counter()
        existing = list(gdir.glob("*.mod")) if gdir.exists() else []
        written = []
        for path, data, how in mods:
            t = title_of(path)
            name = game if len(mods) == 1 else f"{game} - {t}"
            if titles[t] > 1:
                seen[t] += 1
                name += f" ({seen[t]})"
            dest = gdir / f"{name}.mod"
            if any(p.read_bytes() == data for p in existing):
                totals["déjà là"] += 1
                written.append((dest.name, how, "déjà là"))
                continue
            if not a.essai:
                gdir.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
            totals["d'origine" if how == "d'origine" else "convertis"] += 1
            written.append((dest.name, how, ""))
        totals["pas encore lus"] += sum(not_read.values())
        totals["abîmés"] += len(damaged)
        inventory.append((game, archive.name, written, not_read, damaged, len(got)))
        print(f"{game} : {len(mods)} en .mod" + (f", pas encore lus : {dict(not_read)}" if not_read else "")
              + (f", abîmés : {len(damaged)}" if damaged else ""))
    orig = totals["d'origine"]
    print(f"\n{orig} .mod d'origine, {totals['convertis']} convertis, {totals['déjà là']} déjà là, "
          f"{totals['pas encore lus']} pas encore lus, {totals['abîmés']} abîmés")
    if not a.essai:
        write_inventory(a.out / "INVENTAIRE.md", inventory)


def write_inventory(path: pathlib.Path, inventory):
    lines = ["# Inventaire des musiques", "",
             "Fait par `scripts/import_lha.py`. Les originaux de chaque jeu sont dans `<Jeu>\\originaux\\`.", "",
             "| Jeu | Musiques en .mod | Pas encore lues (format) | Remarques |", "|---|---|---|---|"]
    later = collections.Counter()
    for game, arch, written, not_read, damaged, nfiles in inventory:
        conv = sum(1 for _n, how, _ in written if how.startswith("converti"))
        orig = len(written) - conv
        mods = f"{len(written)}" + (f" (dont {conv} convertis)" if conv else "") if written else "—"
        nr = ", ".join(f"{n} {NAMES.get(k, '`' + k + '.`')}" for k, n in not_read.most_common()) or "—"
        notes = f"{len(damaged)} fichier abîmé dans l'archive" if damaged else ""
        lines.append(f"| {game} | {mods} | {nr} | {notes} |")
        later.update(not_read)
    lines += ["", "## Formats pas encore lus", ""]
    lines += [f"- {NAMES[k] + ' (`' + k + '.`)' if k in NAMES else '`' + k + '.`'} : {n} fichier{'s' if n > 1 else ''}"
              for k, n in later.most_common()]
    lines += ["", "Ils sont gardés dans `originaux\\`. Ce sont des musiques à lecteur intégré : il faudra UADE "
              "(émulateur des lecteurs Amiga) pour les écouter, et un décodeur par format pour en tirer les notes "
              "(voir docs/ROADMAP.md).", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
