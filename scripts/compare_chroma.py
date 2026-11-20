"""Compare, fenêtre par fenêtre, les notes présentes dans deux enregistrements (chroma : les 12 notes de la gamme).

    .venv\\Scripts\\python scripts\\compare_chroma.py original.mp3 piano.mp3 [fenêtre en s]

Sert à trouver, sans écouter, les passages où un arrangement (piano…) ne joue pas les mêmes notes que l'original :
une ressemblance basse (cosinus des chromas) signale une fausse note, un accord faux ou un décalage dans le temps.
La batterie de l'original brouille un peu la mesure : on compare des moyennes, pas des valeurs absolues.
"""
from __future__ import annotations
import pathlib
import subprocess
import sys
import numpy as np
import imageio_ffmpeg

SR = 22050


def load(path: pathlib.Path) -> np.ndarray:
    raw = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def chroma(x: np.ndarray, hop: float = 0.1, cents: float = 0.0) -> np.ndarray:
    """(frames, 12) : énergie de chaque note de la gamme, de do1 à do7, toutes les `hop` s ; `cents` : accord de
    l'enregistrement (une musique accordée un quart de ton trop haut se lit avec +50)."""
    n, h = 8192, int(hop * SR)
    win = np.hanning(n)
    fr = np.fft.rfftfreq(n, 1 / SR)
    keep = (fr > 32) & (fr < 2100)
    pc = (np.round(12 * np.log2(fr[keep] / 440) - cents / 100) + 9).astype(int) % 12
    out = []
    for k in range(0, max(1, len(x) - n), h):
        sp = np.abs(np.fft.rfft(x[k:k + n] * win))[keep] ** 2
        out.append(np.bincount(pc, sp, minlength=12))
    c = np.array(out)
    return np.sqrt(c)  # racine : moins dominé par la note la plus forte


def similarity(a: np.ndarray, b: np.ndarray, hop: float, window: float) -> list[tuple[float, float]]:
    """[(début en s, ressemblance de 0 à 1)] par fenêtre."""
    n = min(len(a), len(b))
    step = int(window / hop)
    res = []
    for k in range(0, n - step + 1, step):
        va, vb = a[k:k + step].sum(axis=0), b[k:k + step].sum(axis=0)
        if va.sum() < 1e-6 or vb.sum() < 1e-6:
            continue
        va, vb = va - va.mean(), vb - vb.mean()  # le « fond » commun (bruit, batterie) ne compte pas
        res.append((k * hop, float(va @ vb / (np.linalg.norm(va) * np.linalg.norm(vb) + 1e-12))))
    return res


def compare(original: pathlib.Path, other: pathlib.Path, window: float = 2.0, cents_original: float = 0.0,
            cents_other: float = 0.0) -> list[tuple[float, float]]:
    hop = 0.1
    return similarity(chroma(load(original), hop, cents_original), chroma(load(other), hop, cents_other), hop, window)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    a, b = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    window = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
    cents = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0  # accord de l'original (analyze.tuning_offset)
    res = compare(a, b, window, cents)
    vals = np.array([v for _, v in res])
    print(f"ressemblance moyenne {vals.mean():.2f} ; sous 0,5 : {np.mean(vals < 0.5) * 100:.0f} % des fenêtres")
    for t, v in res:
        flag = "  <-- à vérifier" if v < 0.5 else ""
        print(f"  {int(t // 60)}:{t % 60:04.1f}  {v:+.2f}{flag}")


if __name__ == "__main__":
    main()
