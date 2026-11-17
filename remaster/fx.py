"""Chaîne d'effets d'une piste, décrite dans la fiche d'instruments.

Chaque effet est un objet {"type": ..., paramètres..., "mix": 0..1 (facultatif, mélange avec le son d'avant)} :
- "nam"  : ampli capturé (Neural Amp Modeler), {"model": nom, "input_db": 0} ; le son entre normalisé (crête à −6 dB) ;
- "cab"  : baffle (réponse impulsionnelle), {"ir": nom} ;
- "gain" : {"db": x} ;
- tout effet de Pedalboard par son nom : "HighpassFilter", "LowpassFilter", "PeakFilter", "LowShelfFilter",
  "HighShelfFilter", "Compressor", "Distortion", "Delay", "Chorus", "Reverb", "NoiseGate", "Limiter"… avec ses
  paramètres (ex. {"type": "PeakFilter", "cutoff_frequency_hz": 800, "gain_db": -3, "q": 1}).
"""
from __future__ import annotations
import numpy as np
import pedalboard as pb
from . import nam, library

_NAM_CACHE: dict[str, nam.Model] = {}


def _apply_one(x: np.ndarray, spec: dict, sr: int) -> np.ndarray:
    spec = dict(spec)
    kind = spec.pop("type")
    spec.pop("mix", None)
    spec.pop("comment", None)
    if kind == "nam":
        name = spec["model"]
        if name not in _NAM_CACHE:
            _NAM_CACHE[name] = nam.Model(library.nam_model(name))
        mono = x.mean(axis=0)
        peak = np.percentile(np.abs(mono), 99.95) or 1.0
        mono = mono / peak * 0.5 * 10 ** (spec.get("input_db", 0) / 20)
        y = _NAM_CACHE[name].process(mono)
        return np.stack([y, y]).astype(np.float32)
    if kind == "cab":
        conv = pb.Convolution(str(library.cab_ir(spec["ir"])), mix=1.0)
        return pb.Pedalboard([conv])(x, sr)
    if kind == "gain":
        return x * 10 ** (spec.get("db", 0) / 20)
    cls = getattr(pb, kind, None)
    if cls is None:
        raise ValueError(f"effet inconnu : {kind}")
    return pb.Pedalboard([cls(**spec)])(x, sr)


def apply(x: np.ndarray, chain: list[dict] | None, sr: int) -> np.ndarray:
    for spec in chain or []:
        y = _apply_one(x, spec, sr)
        mix = spec.get("mix")
        if mix is not None:
            n = min(x.shape[1], y.shape[1])
            y = x[:, :n] * (1 - mix) + y[:, :n] * mix
        x = y.astype(np.float32)
    return x
