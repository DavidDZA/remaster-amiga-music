"""Neural Amp Modeler (.nam) en numpy : la capture d'un vrai ampli, sans PyTorch.

Architecture WaveNet de NAM (format 0.5) : des « layer arrays » de convolutions causales dilatées, chacune avec
une entrée de conditionnement (le signal d'entrée), un flux résiduel et une sortie « head » accumulée.
Ordre des poids : celui de NeuralAmpModelerCore (pour chaque array : rechannel, puis pour chaque couche
conv.weight, conv.bias, input_mixer.weight, 1x1.weight, 1x1.bias ; puis head_rechannel ; et head_scale à la fin).
"""
from __future__ import annotations
import json
import numpy as np

ACTIVATIONS = {
    "Tanh": np.tanh,
    "ReLU": lambda x: np.maximum(x, 0),
    "Sigmoid": lambda x: 1 / (1 + np.exp(-x)),
    "Hardtanh": lambda x: np.clip(x, -1, 1),
    "Fasttanh": np.tanh,
}


class _Reader:
    def __init__(self, w):
        self.w = np.asarray(w, np.float32)
        self.i = 0

    def take(self, *shape):
        n = int(np.prod(shape))
        out = self.w[self.i:self.i + n].reshape(shape)
        self.i += n
        return out


class WaveNet:
    def __init__(self, cfg: dict, weights):
        r = _Reader(weights)
        self.arrays = []
        for la in cfg["layers"]:
            ch, k = la["channels"], la["kernel_size"]
            gated = la.get("gated", False)
            mid = 2 * ch if gated else ch
            arr = {
                "rechannel": r.take(ch, la["input_size"]),
                "layers": [],
                "dilations": la["dilations"], "kernel": k, "gated": gated,
                "act": ACTIVATIONS[la["activation"]],
            }
            for _d in la["dilations"]:
                arr["layers"].append({
                    "conv_w": r.take(mid, ch, k),
                    "conv_b": r.take(mid),
                    "mixer_w": r.take(mid, la["condition_size"]),
                    "w1x1": r.take(ch, ch),
                    "b1x1": r.take(ch),
                })
            arr["head_w"] = r.take(la["head_size"], ch)
            arr["head_b"] = r.take(la["head_size"]) if la.get("head_bias") else None
            self.arrays.append(arr)
        self.head_scale = float(r.take(1)[0])
        if r.i != len(r.w):
            raise ValueError(f"modèle NAM : {len(r.w)} poids, {r.i} attendus")
        self.receptive = 1 + sum((a["kernel"] - 1) * sum(a["dilations"]) for a in self.arrays)

    def _run(self, x: np.ndarray) -> np.ndarray:
        """x : (T,) ; renvoie (T,) ; les `receptive` premiers échantillons servent d'amorce."""
        cond = x[None, :]                     # (1, T)
        h = x[None, :]
        head = None
        for a in self.arrays:
            h = a["rechannel"] @ h            # (ch, T)
            acc = None
            for lay, d in zip(a["layers"], a["dilations"]):
                k = a["kernel"]
                z = lay["conv_b"][:, None] + lay["mixer_w"] @ cond
                for j in range(k):
                    shift = (k - 1 - j) * d   # convolution causale : x[t - shift]
                    if shift == 0:
                        z = z + lay["conv_w"][:, :, j] @ h
                    else:
                        z[:, shift:] += lay["conv_w"][:, :, j] @ h[:, :-shift]
                if a["gated"]:
                    c = z.shape[0] // 2
                    post = a["act"](z[:c]) * (1 / (1 + np.exp(-z[c:])))
                else:
                    post = a["act"](z)
                h = h + lay["w1x1"] @ post + lay["b1x1"][:, None]
                acc = post if acc is None else acc + post
            if head is not None:
                acc = acc + head
            head = a["head_w"] @ acc
            if a["head_b"] is not None:
                head = head + a["head_b"][:, None]
        return self.head_scale * head[0]

    def process(self, x: np.ndarray, block: int = 1 << 16) -> np.ndarray:
        """Traite par blocs ; un bloc silencieux (et précédé de silence) donne du silence sans calcul."""
        x = np.asarray(x, np.float32)
        pad = self.receptive
        xp = np.concatenate([np.zeros(pad, np.float32), x])
        # sortie de l'ampli au repos (souvent ~0, parfois une petite constante)
        idle = float(self._run(np.zeros(pad + 1, np.float32))[-1])
        out = np.full_like(x, idle)
        for s in range(0, len(x), block):
            seg = xp[s:s + block + pad]
            if not np.any(seg):
                continue
            out[s:s + block] = self._run(seg)[pad:]
        return out


class Model:
    def __init__(self, path):
        with open(path, encoding="utf-8") as f:
            j = json.load(f)
        if j.get("architecture") != "WaveNet":
            raise ValueError(f"architecture NAM non gérée : {j.get('architecture')}")
        self.net = WaveNet(j["config"], j["weights"])
        self.sample_rate = j.get("sample_rate") or 48000
        meta = j.get("metadata") or {}
        self.loudness = meta.get("loudness")

    def process(self, x: np.ndarray) -> np.ndarray:
        return self.net.process(x)
