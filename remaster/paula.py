"""Les notes de n'importe quelle musique Amiga, lues dans ce que son lecteur envoie à la puce son (Paula).

Les musiques à lecteur intégré (TFMX, David Whittaker, Richard Joseph, lecteurs propres aux jeux…) ne sont pas des
partitions qu'on peut relire : c'est un programme 68000 qui fabrique la musique. UADE fait tourner ce programme dans
un Amiga émulé ; notre version modifiée (scripts/build_uade.py) écrit un journal de ce que le programme envoie à Paula :

- période (hauteur) et volume de chaque voie, adresse et longueur du sample ;
- le démarrage du DMA d'une voie (événement LOOP) = **une note démarre** ;
- à côté, dans <journal>.smp, chaque sample joué, copié depuis la mémoire Amiga.

On en refait un `player.Song` (ticks réguliers de 20 ms par voie) et un `modfile.Module` (les samples) : la même
forme que pour un .mod, donc le remaster et l'analyse des samples marchent tels quels.
Vérifié sur Dr Mario (.mod joué par UADE) : mêmes notes, mêmes hauteurs, mêmes samples que notre lecteur ProTracker.
"""
from __future__ import annotations
import pathlib
import subprocess
import tempfile
import numpy as np
from .modfile import Module, Sample
from .player import Song, Tick

PAULA_CLOCK = 3546895          # horloge de Paula en PAL (Hz)
FRAME = 0.02                   # un tick = une trame vidéo (50 Hz), le rythme de presque tous les lecteurs
VOL, PER, LEN, LCH, LCL, LOOP = 1, 2, 4, 5, 6, 7
ROOT = pathlib.Path(__file__).resolve().parent.parent
UADE = ROOT / "tools" / "uade"


def cyg(p: pathlib.Path) -> str:
    """Chemin vu par UADE (programme MSYS2) : /cygdrive/f/… (un « f: » serait pris pour un volume Amiga)."""
    s = str(pathlib.Path(p).resolve()).replace("\\", "/")
    return f"/cygdrive/{s[0].lower()}{s[2:]}"


def record(music: pathlib.Path, workdir: pathlib.Path, subsong: int = -1, seconds: int = 300) -> dict:
    """Joue la musique avec UADE : son (WAV), journal Paula et samples. Renvoie les chemins et les infos."""
    exe, core = UADE / "bin" / "uade2wav.exe", UADE / "bin" / "uadecore.exe"
    if not core.exists():
        raise SystemExit("UADE absent : lancer  .venv\\Scripts\\python scripts\\build_uade.py")
    wav, log = workdir / "uade.wav", workdir / "uade.paula"
    r = subprocess.run([str(exe), cyg(UADE / "data"), cyg(core), cyg(music), cyg(wav), str(subsong), str(seconds),
                        cyg(log)], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=seconds * 3 + 60)
    if r.returncode != 0:
        raise ValueError(f"UADE ne sait pas jouer {music.name} : {r.stderr.strip()[-200:]}")
    info = {"wav": wav, "log": log, "smp": workdir / "uade.paula.smp"}
    for line in r.stdout.splitlines():
        k, _, v = line.partition(" ")
        info[k] = v.strip()
    info["seconds"] = float(info.get("seconds", 0))
    return info


def subsongs(music: pathlib.Path) -> tuple[int, int]:
    """(premier, dernier) n° de sous-morceau selon UADE."""
    with tempfile.TemporaryDirectory() as tmp:
        exe = UADE / "bin" / "uade2wav.exe"
        r = subprocess.run([str(exe), cyg(UADE / "data"), cyg(UADE / "bin" / "uadecore.exe"), cyg(music),
                            cyg(pathlib.Path(tmp) / "p.wav"), "-1", "1"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
    for line in r.stdout.splitlines():
        if line.startswith("subsongs "):
            _cur, lo, hi = (int(x) for x in line.split()[1:4])
            return lo, hi
    raise ValueError(f"UADE ne reconnaît pas {music.name}")


def events(log: pathlib.Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(temps en s, voie, type, valeur) de chaque écriture dans Paula."""
    raw = log.read_bytes()[16:]
    a = np.frombuffer(raw[: len(raw) // 12 * 12], dtype=[("t", ">u4"), ("b", "u1", 8)])
    t = a["t"].astype(np.int64)
    time = np.cumsum(t & 0x00FFFFFF) / PAULA_CLOCK
    ev = (t & 0x80000000) != 0
    b = a["b"][ev]
    return time[ev], b[:, 0].astype(int), b[:, 1].astype(int), (b[:, 2].astype(int) << 8) | b[:, 3]


def samples(smp: pathlib.Path) -> dict[tuple[int, int], bytes]:
    """{(adresse, longueur en octets): données} des samples copiés par UADE."""
    out = {}
    d = smp.read_bytes() if smp.exists() else b""
    pos = 0
    while pos + 8 <= len(d):
        lc = int.from_bytes(d[pos:pos + 4], "big")
        n = int.from_bytes(d[pos + 4:pos + 8], "big")
        out[(lc, n)] = d[pos + 8:pos + 8 + n]
        pos += 8 + n
    return out


def to_song(ev, smp: dict, duration: float, title: str = "") -> tuple[Module, Song]:
    """Le journal en Module (samples) + Song (ticks de 20 ms par voie), comme un .mod rejoué."""
    times, chans, types, vals = ev
    nframes = int(duration / FRAME) + 1
    keys: dict[tuple[int, int], int] = {}      # (adresse, longueur) → n° de sample (1, 2…)
    loops: dict[int, tuple[int, int]] = {}     # n° de sample → (début de boucle, longueur) en octets
    ticks = [[] for _ in range(4)]
    for c in range(4):
        sel = np.nonzero(chans == c)[0]
        ts, ty, va = times[sel], types[sel], vals[sel]
        frame_of = np.minimum((ts / FRAME).astype(int), nframes - 1)
        lch = lcl = ln = per = 0
        vol = 0
        sample, note_per, end_at = 0, 0, None
        trig_frame, loop_pending = -1, None
        k = 0
        for f in range(nframes):
            trigger = False
            while k < len(ts) and frame_of[k] <= f:
                typ, v = ty[k], va[k]
                if typ == VOL:
                    vol = min(64, v)
                elif typ == PER:
                    per = v
                elif typ == LEN:
                    ln = v
                elif typ == LCH:
                    lch = v
                elif typ == LCL:
                    lcl = v
                elif typ == LOOP:  # le DMA démarre : une note
                    lc = (lch << 16) | lcl
                    nbytes = (ln or 65536) * 2
                    key = (lc, nbytes)
                    if ln <= 1:  # longueur nulle ou d'un mot : un sample vide, qui coupe la voie
                        sample, end_at, loop_pending = 0, None, None
                    elif key in smp:
                        if key not in keys:
                            keys[key] = len(keys) + 1
                        sample = keys[key]
                        trigger, note_per, trig_frame = True, per, f
                        loop_pending = (lc, nbytes, ts[k])
                        end_at = None
                if typ in (LCH, LCL, LEN) and loop_pending and ts[k] - loop_pending[2] < 0.01 and typ == LEN:
                    # juste après le démarrage, le lecteur donne la boucle : 1 mot = pas de boucle
                    lc0, n0, t0 = loop_pending
                    if v <= 1:
                        end_at = t0 + n0 * max(per, 1) / PAULA_CLOCK
                        loops.setdefault(sample, (0, 0))
                    else:
                        loops.setdefault(sample, (max(0, ((lch << 16) | lcl) - lc0), v * 2))
                    loop_pending = None
                k += 1
            playing = sample
            if end_at is not None and f * FRAME >= end_at and not trigger:
                playing = 0
            ticks[c].append(Tick(f * FRAME, playing, float(per) if playing else 0.0, vol, trigger,
                                 note_per if playing else 0))
            if trig_frame == f and not trigger:
                trig_frame = -1
    mod_samples = []
    for (lc, n), idx in sorted(keys.items(), key=lambda kv: kv[1]):
        data = np.frombuffer(smp[(lc, n)], dtype=np.int8).copy()
        ls, ll = loops.get(idx, (0, 0))
        mod_samples.append(Sample(idx, f"sample {idx} (adresse {lc:06x})", data, 0, 64, ls, ll))
    mod = Module(title, 4, mod_samples, [0], 0, [])
    tick_times = [f * FRAME for f in range(nframes)]
    rows = [(0, f % 64, f * FRAME) for f in range(nframes)]
    return mod, Song(4, ticks, tick_times, duration, rows)


def align(ev) -> tuple:
    """Le journal compte aussi le démarrage de l'Amiga émulé : le temps zéro devient la première note.
    Renvoie (événements recalés, décalage en secondes)."""
    times, chans, types, vals = ev
    starts = times[types == LOOP]
    shift = float(starts[0]) if len(starts) else 0.0
    return (np.maximum(0.0, times - shift), chans, types, vals), shift


def trimmed_wav(wav: pathlib.Path, dest: pathlib.Path):
    """Le son d'UADE sans le silence du début (même temps zéro que les notes : la première)."""
    import soundfile as sf
    x, sr = sf.read(wav, dtype="float32", always_2d=True)
    loud = np.nonzero(np.abs(x).max(axis=1) > 1e-4)[0]
    sf.write(dest, x[loud[0]:] if len(loud) else x, sr, subtype="PCM_16")


def find_loop(ev, min_loop: float = 5.0, tol: float = 0.05, rare: float = 0.01) -> tuple[float, float] | None:
    """(début A, durée L) de la boucle : à partir de A, chaque note (voie, longueur du sample, hauteur) revient L s plus
    tard, jusqu'à la fin de l'enregistrement (au moins un tour complet de confirmation). None si rien ne se répète.

    ev : événements recalés (align). On compare la suite des notes décalée de k notes : la plus petite boucle dont
    la répétition couvre toute la fin, avec un écart de temps constant (à `tol` s près)."""
    times, chans, types, vals = ev
    # état de chaque voie au moment de chaque note : adresse du sample, longueur, période
    lc = np.zeros(4, np.int64)
    ln = np.zeros(4, np.int64)
    per = np.zeros(4, np.int64)
    tok, tt = [], []
    for t, c, k, v in zip(times, chans, types, vals):
        if c > 3:
            continue
        if k == LCH:
            lc[c] = (lc[c] & 0xFFFF) | (v << 16)
        elif k == LCL:
            lc[c] = (lc[c] & ~0xFFFF) | v
        elif k == LEN:
            ln[c] = v
        elif k == PER:
            per[c] = v
        elif k == LOOP and ln[c] > 1:
            # sans l'adresse du sample : beaucoup de lecteurs fabriquent leurs sons dans des tampons qui bougent
            tok.append(hash((int(c), int(ln[c]), int(per[c]))))
            tt.append(t)
    n = len(tok)
    if n < 20:
        return None
    tok = np.array(tok, np.int64)
    tt = np.array(tt, float)
    # l'enregistrement s'arrête net : la ou les dernières notes peuvent être incomplètes, on ne les compare pas
    end = tt[-1]
    n = int(np.searchsorted(tt, end - 2.0, side="right"))
    if n < 20:
        return None
    tok, tt = tok[:n], tt[:n]
    end = tt[-1]
    for k in range(1, n // 2):
        same = tok[:-k] == tok[k:]
        m = n - k
        # à partir de i0, au plus `rare` des notes diffèrent de celles k notes plus loin : certaines musiques tirent au
        # sort quelques notes (roulements, effets). Un vrai changement de partie en fait différer bien plus.
        suffix_bad = np.cumsum((~same)[::-1])[::-1]
        ok = np.nonzero(suffix_bad <= rare * (m - np.arange(m)))[0]
        if not len(ok):
            continue
        matches = np.nonzero(same[ok[0]:])[0]
        if not len(matches):
            continue
        i0 = int(ok[0] + matches[0])                # la boucle commence à la première note qui revient
        if i0 >= m - 1:
            continue
        sel = np.nonzero(same[i0:])[0] + i0
        shift = tt[sel + k] - tt[sel]
        L = float(np.median(shift))
        if L < min_loop or np.abs(shift - L).max() > tol:
            continue
        A = float(tt[i0])
        if end - A < 2 * L - tol:                   # la répétition doit couvrir un tour entier
            continue
        if A > end / 2:                             # une vraie boucle commence tôt (après l'intro), pas à la fin
            continue
        return A, L
    return None


def load(music: pathlib.Path, subsong: int = -1, seconds: int = 300, keep: pathlib.Path | None = None):
    """(Module, Song, infos UADE) d'une musique de n'importe quel format. keep : dossier où garder le son d'UADE."""
    with tempfile.TemporaryDirectory() as tmp:
        info = record(music, pathlib.Path(tmp), subsong, seconds)
        ev, shift = align(events(info["log"]))
        mod, song = to_song(ev, samples(info["smp"]), max(1.0, info["seconds"] - shift), music.name)
        if keep is not None:
            keep.mkdir(parents=True, exist_ok=True)
            trimmed_wav(info["wav"], keep / "uade.wav")
        info = {k: v for k, v in info.items() if not isinstance(v, pathlib.Path)}
    return mod, song, info
