"""Enregistre en MP3 les musiques Amiga que le projet ne sait pas encore convertir en .mod, avec UADE.

    .venv\\Scripts\\python scripts\\render_uade.py                 # tous les jeux de in\\music\\
    .venv\\Scripts\\python scripts\\render_uade.py "Turrican 3"    # un jeu

Ce sont les musiques à lecteur intégré (TFMX, David Whittaker, Richard Joseph, `cust`…) : UADE émule l'Amiga et
le vrai lecteur de chaque format (tools\\uade, construit par scripts\\build_uade.py). Pour chaque fichier de
in\\music\\<Jeu>\\originaux\\ qui n'a pas de .mod, chaque sous-morceau devient
out\\<Jeu> - <titre>[ (n)]\\<Jeu> - <titre>[ (n)] (original).mp3 (un dossier par musique, comme les remasters).

Fin d'un morceau : quand le lecteur la signale, après 5 s de silence, ou au bout de --max secondes (300 par défaut :
beaucoup de musiques de jeux bouclent sans fin). Les sous-morceaux muets ou de moins de 3 s (bruitages) sont
écartés. Le compte rendu va dans in\\music\\AUDIO-UADE.md.
"""
from __future__ import annotations
import argparse
import concurrent.futures as cf
import importlib.util
import pathlib
import subprocess
import sys
import tempfile
import numpy as np
import soundfile as sf

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from remaster import render  # noqa: E402

UADE = ROOT / "tools" / "uade"
spec = importlib.util.spec_from_file_location("import_lha", ROOT / "scripts" / "import_lha.py")
imp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(imp)


def cyg(p: pathlib.Path) -> str:
    """Chemin vu par UADE (programme MSYS2) : /cygdrive/f/… (un « f: » serait pris pour un volume Amiga)."""
    s = str(pathlib.Path(p).resolve()).replace("\\", "/")
    return f"/cygdrive/{s[0].lower()}{s[2:]}"


def uade(music: pathlib.Path, wav: pathlib.Path, subsong: int, seconds: int) -> dict:
    exe = UADE / "bin" / "uade2wav.exe"
    if not exe.exists():
        raise SystemExit("UADE absent : lancer  .venv\\Scripts\\python scripts\\build_uade.py")
    r = subprocess.run([str(exe), cyg(UADE / "data"), cyg(UADE / "bin" / "uadecore.exe"), cyg(music), cyg(wav),
                        str(subsong), str(seconds)], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=seconds * 3 + 60)
    info = {"ok": r.returncode == 0}
    for line in r.stdout.splitlines():
        key, _, val = line.partition(" ")
        info[key] = val.strip()
    return info


def candidates(gdir: pathlib.Path) -> list[pathlib.Path]:
    """Les musiques de originaux\\ qui n'ont pas de .mod (ni d'origine ni converti)."""
    out = []
    for f in sorted((gdir / "originaux").rglob("*")):
        if not f.is_file():
            continue
        kind = imp.music_kind(f.name)
        if kind in imp.COMPANIONS or kind == "?":
            continue
        data = f.read_bytes()
        if (kind == "mod" and imp.plays(data) is None) or imp.convert(data, imp.title_of(f.name))[0] is not None:
            continue
        out.append(f)
    return out


def render_one(game: str, music: pathlib.Path, out_root: pathlib.Path, seconds: int, essai: bool) -> list:
    """Tous les sous-morceaux d'un fichier : [(nom, secondes, lecteur)] ou [(nom, None, raison)]."""
    title = f"{game} - {imp.title_of(music.name)}"
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        probe = uade(music, pathlib.Path(tmp, "p.wav"), -1, 1)
        if not probe["ok"] or "subsongs" not in probe:
            return [(title, None, "UADE ne reconnaît pas ce fichier")]
        _cur, lo, hi = (int(x) for x in probe["subsongs"].split())
        subs = list(range(lo, hi + 1))
        for k, s in enumerate(subs):
            name = title if len(subs) == 1 else f"{title} ({k + 1})"
            wav = pathlib.Path(tmp, f"{s}.wav")
            info = uade(music, wav, s, seconds)
            if not info["ok"] or not wav.exists():
                results.append((name, None, "lecture impossible"))
                continue
            x, sr = sf.read(wav, dtype="float32", always_2d=True)
            loud = np.where(np.abs(x).max(axis=1) > 10 ** (-50 / 20))[0]
            if len(loud) == 0 or (loud[-1] - loud[0]) / sr < 3:
                continue  # muet, ou bruitage de moins de 3 s
            x = x[loud[0]: loud[-1] + sr // 2]
            secs = len(x) / sr
            if not essai:
                d = out_root / imp.clean(name)
                d.mkdir(parents=True, exist_ok=True)
                clean_wav = pathlib.Path(tmp, f"{s}-c.wav")
                sf.write(clean_wav, x, sr, subtype="PCM_16")
                render.to_mp3(clean_wav, d / f"{imp.clean(name)} (original).mp3",
                              {"title": name, "album": game, "comment": f"Original Amiga ({info.get('player', '')}), "
                               "enregistré avec UADE"}, -14)
            results.append((name, round(secs), info.get("player") or info.get("format") or "?"))
    return results


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="MP3 des musiques Amiga à lecteur intégré (UADE).")
    ap.add_argument("jeux", nargs="*", help="noms de dossiers de in\\music (tous par défaut)")
    ap.add_argument("--music", type=pathlib.Path, default=ROOT / "in" / "music")
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "out")
    ap.add_argument("--max", type=int, default=300, help="durée maximale d'un morceau (secondes)")
    ap.add_argument("--essai", action="store_true", help="ne rien écrire")
    a = ap.parse_args()
    games = [d for d in sorted(a.music.iterdir()) if d.is_dir() and (not a.jeux or d.name in a.jeux)]
    jobs = [(g.name, f) for g in games for f in candidates(g)]
    print(f"{len(jobs)} fichiers à enregistrer avec UADE")
    report: dict[str, list] = {}
    with cf.ThreadPoolExecutor(max_workers=6) as pool:
        futs = {pool.submit(render_one, g, f, a.out, a.max, a.essai): (g, f) for g, f in jobs}
        for fut in cf.as_completed(futs):
            g, f = futs[fut]
            try:
                res = fut.result()
            except Exception as e:  # noqa: BLE001
                res = [(f"{g} - {f.name}", None, f"erreur : {e}")]
            report.setdefault(g, []).extend(res)
            ok = [r for r in res if r[1] is not None]
            print(f"  {g} / {f.name} : {len(ok)} morceau(x)" + ("" if ok else f" — {res[0][2] if res else 'rien'}"))
    total = sum(1 for rs in report.values() for r in rs if r[1] is not None)
    print(f"\n{total} MP3 enregistrés")
    if not a.essai and not a.jeux:
        lines = ["# Musiques enregistrées avec UADE", "",
                 "Fait par `scripts/render_uade.py` : les originaux Amiga à lecteur intégré, en MP3, dans "
                 "`out\\<nom>\\<nom> (original).mp3`. Remaster : `python -m remaster <fichier> --sous-morceau N` "
                 "(n° entre parenthèses dans le nom). Pas encore de partitions pour celles-ci.",
                 "", "| Jeu | Morceau | Durée | Lecteur |", "|---|---|---|---|"]
        for g in sorted(report):
            for name, secs, how in sorted(report[g]):
                dur = f"{secs // 60}:{secs % 60:02d}" if secs is not None else "—"
                lines.append(f"| {g} | {name} | {dur} | {how} |")
        (a.music / "AUDIO-UADE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
