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
                    if ln <= 1 or per == 0:  # sample vide (coupe la voie), ou note sans hauteur encore écrite
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


TWO_LOOPS_BELOW = 120   # comme scripts/render_originals.py : un tour plus court que ça, on en joue deux
FADE = 4


def on_grid(mod: Module, song: Song, ev, eighth_max_bpm: float = 220) -> tuple[Module, Song, dict]:
    """Une grille de lignes et de mesures pour une musique lue par UADE (les partitions en ont besoin), et la même
    longueur que son MP3 d'origine : un tour de boucle, ou deux s'il fait moins de 2 min, plus le fondu.

    Pas de la grille : l'écart le plus fréquent entre deux notes (en trames de 20 ms) est pris pour une croche
    (une ligne = une double croche, comme un .mod), sauf si ça donne une noire à plus de `eighth_max_bpm` : c'est
    alors une double croche. Le temps zéro est la première note."""
    notes = [(i, c, t.note_period) for c, ch in enumerate(song.ticks) for i, t in enumerate(ch) if t.trigger]
    frames = sorted({i for i, _c, _p in notes})
    gaps = np.diff(frames)
    gaps = gaps[gaps > 0]
    step = int(np.bincount(gaps).argmax()) if len(gaps) else 6
    # valeur de l'écart le plus fréquent : croche, double, triple croche… la première qui donne une noire à
    # `eighth_max_bpm` au plus (un lecteur TFMX qui orne ses notes toutes les 2 trames ne joue pas à ♩ = 375)
    row_frames = step
    for m in (0.5, 1, 2, 4, 8):
        rf = step * m
        if rf >= 1 and rf == int(rf) and 60 / (4 * rf * FRAME) <= eighth_max_bpm:
            row_frames = int(rf)
            break
    row = row_frames * FRAME
    bar_frames = 16 * row_frames
    # phase de la grille : le décalage qui met le plus de notes pile sur une ligne
    fr = np.array(frames)
    phase = max(range(row_frames), key=lambda o: int(np.sum((fr - o) % row_frames == 0)))
    # barre de mesure : sur les temps forts, là où démarrent les notes longues (et les notes graves)
    dur: dict[tuple[int, int], int] = {}
    by_ch: dict[int, list[int]] = {}
    for i, c, _p in notes:
        by_ch.setdefault(c, []).append(i)
    for c, lst in by_ch.items():
        for k, i in enumerate(lst):
            dur[(c, i)] = (lst[k + 1] if k + 1 < len(lst) else i + bar_frames) - i
    weight = np.zeros(bar_frames)
    for (c, i), d in dur.items():
        weight[i % bar_frames] += min(d, bar_frames) / row_frames
    downbeat = max(range(phase, bar_frames, row_frames),
                   key=lambda d: weight[d] + 0.5 * weight[(d + 4 * row_frames) % bar_frames]
                   + weight[(d + 8 * row_frames) % bar_frames] + 0.5 * weight[(d + 12 * row_frames) % bar_frames])
    pad = (bar_frames - downbeat) % bar_frames   # silence ajouté au début : la ligne 0 tombe sur un premier temps
    loop = find_loop(ev)
    if loop is None:
        a, length, passes, total = 0.0, 0.0, 1, min(song.duration, 300.0)
    else:
        a, length = loop
        passes = 1 if a + length >= TWO_LOOPS_BELOW else 2
        total = min(song.duration, a + passes * length + FADE)
    nframes = int(total / FRAME) + 1
    blank = [Tick(0.0, 0, 0.0, 0, False, 0)] * pad
    ticks = [[Tick(k * FRAME, t.sample, t.period, t.volume, t.trigger, t.note_period)
              for k, t in enumerate(blank + ch[:nframes])] for ch in song.ticks]
    total += pad * FRAME
    nrows = int((total - 1e-6) / row) + 1   # la dernière ligne commence avant la fin
    rows = [(i // 128, i % 128, i * row) for i in range(nrows)]
    new = Song(song.channels, ticks, [k * FRAME for k in range(len(ticks[0]))], total, rows)
    mod = Module(mod.title, mod.channels, mod.samples, list(range(rows[-1][0] + 1)), 0, [])
    per_pass = length / row / 16 if loop else 0
    whole = loop is not None and abs(per_pass - round(per_pass)) < 0.05
    info = {"pas_trames": step, "ligne_s": row, "noire_bpm": round(60 / (4 * row) + 1e-6),
            "boucle": loop, "tours": passes, "mesures_par_tour": per_pass, "decalage_s": pad * FRAME,
            # reprise : un tour = un nombre entier de mesures ; elle commence à la première barre après le début
            # de la boucle (ce qui précède est une levée, écrite une fois)
            "reprise": passes == 2 and whole,
            "reprise_debut": int(np.ceil(((a + pad * FRAME) / row - 1e-6) / 16)) if loop else 0,
            "fondu": FADE if loop else 0.0}
    return mod, new, info


def load_grid(music: pathlib.Path, subsong: int = -1, seconds: int = 1200):
    """(Module, Song sur une grille de lignes, infos) : pour les partitions et le piano (voir on_grid)."""
    with tempfile.TemporaryDirectory() as tmp:
        info = record(music, pathlib.Path(tmp), subsong, seconds)
        ev, shift = align(events(info["log"]))
        mod, song = to_song(ev, samples(info["smp"]), max(1.0, info["seconds"] - shift), music.name)
    return on_grid(mod, song, ev)


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
