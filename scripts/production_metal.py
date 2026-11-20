"""Une production « métal » appliquée à la fiche d'une musique, partie par partie (20/11/2026).

    .venv\\Scripts\\python scripts\\production_metal.py "in\\music\\Dr Mario\\Dr Mario.mod" batterie=1,2 basse=3 rythmique=11,12 lead=5 autres=10

Claude ne peut pas écouter : ce sont des recettes de mixage métal connues, pas des réglages faits à l'oreille.
- jeu humanisé (midi.humanize) : attaques qui bougent de quelques ms, force qui varie, accords grattés corde par
  corde, et deux prises différentes à gauche et à droite pour les guitares doublées ;
- batterie : compression parallèle (le son compressé à fond mêlé au son normal : plus de corps sans perdre l'attaque),
  charleston et crashs ajoutés moins réguliers ;
- basse : graves propres sous 200 Hz + copie saturée dans les médiums (la basse s'entend sous les guitares sans
  baver) ;
- mix : compression plus marquée, un peu d'air dans les aigus, niveau −11 LUFS (au lieu de −14).
Les réglages de chaque partie sont remplacés à chaque lancement (pas d'empilement).
"""
from __future__ import annotations
import copy
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from remaster import render  # noqa: E402
from remaster.__main__ import open_music  # noqa: E402

HUMAN = {
    "batterie": {"timing_ms": 2, "velocity": 5},
    "basse": {"timing_ms": 3, "velocity": 6},
    "rythmique": {"timing_ms": 4, "velocity": 6, "strum_ms": 3},
    "lead": {"timing_ms": 5, "velocity": 8},
    "autres": {"timing_ms": 8, "velocity": 6},
}
SMASH = {"type": "Compressor", "threshold_db": -32, "ratio": 10, "attack_ms": 1, "release_ms": 60}
BASS_FX = [
    {"type": "HighpassFilter", "cutoff_frequency_hz": 35},
    {"type": "parallel", "branches": [
        {"fx": [{"type": "LowpassFilter", "cutoff_frequency_hz": 200},
                {"type": "Compressor", "threshold_db": -20, "ratio": 4, "attack_ms": 10, "release_ms": 120}]},
        {"fx": [{"type": "HighpassFilter", "cutoff_frequency_hz": 250},
                {"type": "Distortion", "drive_db": 28},
                {"type": "LowpassFilter", "cutoff_frequency_hz": 4500},
                {"type": "PeakFilter", "cutoff_frequency_hz": 1200, "gain_db": 2, "q": 1.0}], "gain_db": -6},
    ]},
    {"type": "Compressor", "threshold_db": -18, "ratio": 3, "attack_ms": 5, "release_ms": 100},
]


def unwrap_parallel(fx: list) -> list:
    """La chaîne d'origine, si elle a déjà été mise en parallèle par ce script."""
    if len(fx) == 1 and fx[0].get("type") == "parallel" and fx[0].get("comment") == "compression parallèle":
        return copy.deepcopy(fx[0]["branches"][0]["fx"])
    return fx


def drum_fx(fx: list) -> list:
    base = unwrap_parallel(copy.deepcopy(fx or []))
    return [{"type": "parallel", "comment": "compression parallèle", "branches": [
        {"fx": base}, {"fx": base + [SMASH], "gain_db": -4}]}]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    music = pathlib.Path(sys.argv[1])
    m = open_music(music)
    cfg = render.load_config(m.cfg_path)
    for arg in sys.argv[2:]:
        role, _, ids = arg.partition("=")
        if role not in HUMAN:
            raise SystemExit(f"partie inconnue : {role} (parties : {', '.join(HUMAN)})")
        for s in ids.split(","):
            inst = cfg["samples"][s]
            inst["humanize"] = dict(HUMAN[role])
            if role == "batterie":
                inst["fx"] = drum_fx(inst.get("fx"))
            elif role == "basse":
                inst["fx"] = copy.deepcopy(BASS_FX)
            if inst.get("double"):
                inst["double"]["delay_ms"] = 0  # le décalage vient maintenant du jeu de chaque prise
            print(f"sample {s} ({inst.get('name', '?')}) : {role}")
        if role == "batterie":
            for k in ("hihat", "crash"):
                if k in cfg.get("extras", {}):
                    cfg["extras"][k]["humanize"] = {"timing_ms": 3, "velocity": 10}
    master = cfg.setdefault("master", {})
    master["loudness"] = -11
    master["comp_threshold"] = -20
    master["fx"] = [f for f in master.get("fx", []) if f.get("type") != "HighShelfFilter"] + \
        [{"type": "HighShelfFilter", "cutoff_frequency_hz": 8000, "gain_db": 1.5}]
    m.cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"→ {m.cfg_path}")


if __name__ == "__main__":
    main()
