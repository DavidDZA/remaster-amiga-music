"""Enregistre en MP3 l'original de toutes les musiques, rangées par jeu : out\\<Jeu>\\<musique> (original).mp3.

    .venv\\Scripts\\python scripts\\render_originals.py                 # tous les jeux de in\\music\\
    .venv\\Scripts\\python scripts\\render_originals.py "Turrican 3"    # un jeu
    .venv\\Scripts\\python scripts\\render_originals.py --refaire       # même ce qui existe déjà

- les .mod de in\\music\\<Jeu>\\ (d'origine ou convertis) : joués par OpenMPT, une fois du début à la fin ;
- les musiques à lecteur intégré de in\\music\\<Jeu>\\originaux\\ (TFMX, David Whittaker, Richard Joseph, `cust`…) :
  jouées par UADE, qui émule l'Amiga et le vrai lecteur du format (tools\\uade, scripts\\build_uade.py). Chaque
  sous-morceau donne un MP3 « <Jeu> - <titre> (n) ». Fin : quand le lecteur l'annonce, ou après 5 s de silence ;
  une musique qui boucle sans fin (beaucoup) est jouée une fois, ou deux si un tour fait moins de 2 min, avec un
  fondu de 4 s (boucle trouvée dans le journal de la puce son : remaster/paula.py, find_loop). Les morceaux de moins de 15 s (jingles, bruitages) ne sont pas gardés (--min).

Toutes les musiques d'un jeu sont à plat dans out\\<Jeu>\\ ; une musique qu'on retravaille a en plus son sous-dossier
out\\<Jeu>\\<musique>\\ (remasters, piano, partitions). Compte rendu : in\\music\\ECOUTE.md.
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
from remaster import render, modfile, player  # noqa: E402

MIN_SECONDS = 15  # plus court : un jingle ou un bruitage, pas gardé
TWO_LOOPS_BELOW = 120  # un tour de boucle plus court que ça : on en joue deux
FADE = 4  # fondu de fin (secondes) après la coupe à la boucle
FALLBACK = 300  # boucle introuvable : on garde les 5 premières minutes

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


def mp3_seconds(mp3: pathlib.Path) -> float:
    """Durée réelle d'un MP3 (lue par ffmpeg)."""
    import re
    import imageio_ffmpeg
    r = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(mp3)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


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


def render_mod(game: str, mod: pathlib.Path, out_root: pathlib.Path, again: bool,
               min_s: float = MIN_SECONDS) -> list:
    dest = out_root / game / f"{mod.stem} (original).mp3"
    if dest.exists() and not again:
        return [(mod.stem, "déjà là", "OpenMPT")]
    m = modfile.load(mod)
    if player.play(m).duration < min_s:
        return [(mod.stem, f"moins de {min_s:g} s", "OpenMPT")]
    dest.parent.mkdir(parents=True, exist_ok=True)
    render.render_original(mod, out_root / game, {"title": mod.stem, "album": game,
                                                  "comment": f"Original Amiga ({m.title or mod.name})"})
    if mp3_seconds(dest) < min_s:  # OpenMPT peut finir plus tôt que notre lecteur : on juge sur le MP3
        dest.unlink()
        return [(mod.stem, f"moins de {min_s:g} s", "OpenMPT")]
    return [(mod.stem, "ok", "OpenMPT")]


def looped_badly(mp3: pathlib.Path) -> bool:
    """MP3 UADE à refaire avec --boucles : coupé à 5 min, ou boucle de plus de 10 min (fausse boucle trouvée en fin
    d'enregistrement par une version précédente)."""
    import re
    import imageio_ffmpeg
    e = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(mp3)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace").stderr
    seconds = mp3_seconds(mp3)
    if "UADE" not in e:
        return False
    return (FALLBACK - 5 <= seconds <= FALLBACK + 10) or ("boucle 1 fois" in e and seconds > 600)


def cut_at_loop(x: np.ndarray, sr: int, log_ev, natural_end: bool) -> tuple[np.ndarray, str]:
    """Une musique qui boucle sans fin : un tour de boucle, ou deux si un tour fait moins de TWO_LOOPS_BELOW
    secondes (et tant pis si c'est encore court) ; un fondu de FADE s, pris sur la suite, évite une coupure sèche.
    Sans boucle trouvée : les FALLBACK premières secondes. x commence à la première note (comme le journal)."""
    from remaster import paula
    if natural_end:
        return x, "fin du morceau"
    loop = paula.find_loop(log_ev)
    if loop is None:
        cut, how = FALLBACK, f"pas de boucle trouvée : {FALLBACK // 60} min"
    else:
        a, length = loop
        cut, how = a + length, "boucle 1 fois"
        if cut < TWO_LOOPS_BELOW:
            cut, how = a + 2 * length, "boucle 2 fois"
    end = min(len(x), int((cut + FADE) * sr))
    y = x[:end].copy()
    f0 = min(int(cut * sr), end)
    if end > f0:
        y[f0:end] *= np.linspace(1.0, 0.0, end - f0, dtype=np.float32)[:, None]
    return y, how


def render_uade(game: str, music: pathlib.Path, out_root: pathlib.Path, seconds: int, again: bool,
                min_s: float = MIN_SECONDS, redo_long: bool = False, only: int | None = None) -> list:
    """Les sous-morceaux d'un fichier (ou seulement le n° `only`, compté depuis 0) : [(nom, état, lecteur)]."""
    from remaster import paula
    title = f"{game} - {imp.uade_title(music)}"
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        probe = uade(music, pathlib.Path(tmp, "p.wav"), -1, 1)
        if not probe["ok"] or "subsongs" not in probe:
            return [(title, "UADE ne reconnaît pas ce fichier", "")]
        _cur, lo, hi = (int(x) for x in probe["subsongs"].split())
        subs = list(range(lo, hi + 1))
        for k, s in enumerate(subs):
            if only is not None and k != only:
                continue
            name = imp.clean(title if len(subs) == 1 else f"{title} ({k + 1})")
            dest = out_root / game / f"{name} (original).mp3"
            if dest.exists() and not again and not (redo_long and looped_badly(dest)):
                results.append((name, "déjà là", "UADE"))
                continue
            work = pathlib.Path(tmp, str(s))
            work.mkdir()
            try:
                info = paula.record(music, work, s, seconds)  # son + journal de la puce son (pour la boucle)
            except ValueError:
                results.append((name, "lecture impossible", ""))
                continue
            x, sr = sf.read(info["wav"], dtype="float32", always_2d=True)
            loud = np.where(np.abs(x).max(axis=1) > 10 ** (-50 / 20))[0]
            if len(loud) == 0 or (loud[-1] - loud[0]) / sr < min_s:
                continue  # muet, ou jingle / bruitage trop court
            x = x[loud[0]: loud[-1] + sr // 2]
            ev, _shift = paula.align(paula.events(info["log"]))
            x, how = cut_at_loop(x, sr, ev, natural_end=info["seconds"] < seconds - 1)
            if len(x) / sr < min_s:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            clean_wav = pathlib.Path(tmp, f"{s}-c.wav")
            sf.write(clean_wav, x, sr, subtype="PCM_16")
            player = info.get("player") or info.get("format") or "?"
            render.to_mp3(clean_wav, dest, {"title": name, "album": game,
                                            "comment": f"Original Amiga ({player}), enregistré avec UADE ; {how}"}, -14)
            results.append((name, "ok", f"{player} ({how})"))
    return results


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="MP3 des originaux de toutes les musiques, rangés par jeu.")
    ap.add_argument("jeux", nargs="*", help="noms de dossiers de in\\music (tous par défaut)")
    ap.add_argument("--music", type=pathlib.Path, default=ROOT / "in" / "music")
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "out")
    ap.add_argument("--max", type=int, default=1200,
                    help="enregistrement maximal d'un morceau lu par UADE, pour trouver sa boucle (secondes)")
    ap.add_argument("--boucles", action="store_true",
                    help="refaire les MP3 UADE coupés à 5 min (règle de la boucle)")
    ap.add_argument("--min", type=float, default=MIN_SECONDS, help="durée minimale gardée (secondes)")
    ap.add_argument("--refaire", action="store_true", help="refaire aussi les MP3 qui existent déjà")
    a = ap.parse_args()
    games = [d for d in sorted(a.music.iterdir()) if d.is_dir() and (not a.jeux or d.name in a.jeux)]
    jobs = [("mod", g.name, f, None) for g in games for f in sorted(g.glob("*.mod"))]
    from remaster import paula
    for g in games:
        for f in candidates(g):
            try:
                lo, hi = paula.subsongs(f)
            except ValueError:
                lo, hi = 0, 0
            jobs += [("uade", g.name, f, k) for k in range(hi - lo + 1)]  # un travail par sous-morceau
    print(f"{len(jobs)} morceaux ({sum(j[0] == 'mod' for j in jobs)} .mod, {sum(j[0] == 'uade' for j in jobs)} UADE)",
          flush=True)
    report: dict[str, list] = {}
    with cf.ThreadPoolExecutor(max_workers=6) as pool:
        futs = {}
        for kind, g, f, k in jobs:
            fn = (lambda g=g, f=f: render_mod(g, f, a.out, a.refaire, a.min)) if kind == "mod" else \
                 (lambda g=g, f=f, k=k: render_uade(g, f, a.out, a.max, a.refaire, a.min, a.boucles, k))
            futs[pool.submit(fn)] = (g, f)
        for fut in cf.as_completed(futs):
            g, f = futs[fut]
            try:
                res = fut.result()
            except Exception as e:  # noqa: BLE001
                res = [(f"{g} - {f.name}", f"erreur : {e}", "")]
            report.setdefault(g, []).extend(res)
    made = sum(1 for rs in report.values() for r in rs if r[1] == "ok")
    kept = sum(1 for rs in report.values() for r in rs if r[1] == "déjà là")
    print(f"{made} MP3 enregistrés, {kept} déjà là")
    if not a.jeux:
        lines = ["# Les musiques en MP3", "",
                 "Fait par `scripts/render_originals.py`. Toutes les musiques d'un jeu sont dans `out\\<Jeu>\\`.", "",
                 "| Jeu | Musique | Lu par | Remarque |", "|---|---|---|---|"]
        for g in sorted(report):
            for name, state, how in sorted(report[g]):
                if state.startswith("moins de"):
                    continue
                note = "" if state in ("ok", "déjà là") else state
                lines.append(f"| {g} | {name} | {how} | {note} |")
        (a.music / "ECOUTE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
