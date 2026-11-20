"""Une liste d'extraits à écouter pour choisir un son : le même passage de la musique, dans le mix complet, avec à
chaque fois un autre son pour un sample. L'utilisateur écoute et donne un numéro.

    .venv\\Scripts\\python scripts\\extraits.py "in\\music\\Dr Mario\\Dr Mario.mod"

Les candidats sont dans songs\\extraits\\<musique>.json :
    {"duree": 20, "samples": {"5": {"titre": "Lead", "debut": 40 (facultatif), "candidats": [
        {"nom": "actuel …"},                                   le son de la fiche, tel quel (toujours le n° 0)
        {"nom": "…", "nam": "<ampli NAM>"},                    la fiche, avec un autre ampli
        {"nom": "…", "surge": "Leads/Classic Lead 1"},         un preset de Surge XT (usine ou autres auteurs)
        {"nom": "…", "remplace": {…réglages d'un sample…}}     n'importe quel autre réglage de la fiche
    ]}}}

Résultat : out\\Retravaillées\\<musique>\\extraits\\<titre> <n> - <nom>.mp3. Chaque candidat est mis au niveau du son
actuel sur ce passage : seul le son change, pas le volume. Version « fidèle » (sans les ajouts de batterie).
Le passage : 20 s où ce sample joue le plus de notes (ou « debut »).
"""
from __future__ import annotations
import copy
import json
import pathlib
import sys
import numpy as np
import soundfile as sf

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from remaster import render, reference, vst  # noqa: E402
from remaster.__main__ import open_music  # noqa: E402
from remaster.choisir import excerpt  # noqa: E402
from essai_vst import make_state, BEND  # noqa: E402

SR = render.SR
PRE = 1.0  # seconde jouée avant le passage (attaques, réverbération), coupée ensuite


def busiest_start(times: list[float], length: float) -> float:
    """L'attaque à partir de laquelle ce sample joue le plus de notes en `length` secondes."""
    ts = sorted(times)
    best, best_n, j = ts[0], 0, 0
    for i, t in enumerate(ts):
        while j < len(ts) and ts[j] < t + length:
            j += 1
        if j - i > best_n:
            best, best_n = t, j - i
    return best


def window(audio: np.ndarray, start: float, length: float) -> np.ndarray:
    a, n = int(start * SR), int(length * SR)
    out = np.zeros((2, n), np.float32)
    piece = audio[:, max(0, a):a + n]
    out[:, :piece.shape[1]] = piece
    return out


def energy(stems) -> float:
    return sum(reference.weighted_energy(a.mean(axis=0), SR) * (g * 10 ** (inst.gain_db / 20)) ** 2
               for a, inst, _, g in stems)


def candidate_cfg(cfg: dict, sample: str, cand: dict, music_name: str, k: int) -> dict:
    out = copy.deepcopy(cfg)
    base = out["samples"][sample]
    if "nam" in cand:
        for f in base.get("fx", []):
            if f.get("type") == "nam":
                f["model"] = cand["nam"]
    elif "surge" in cand:
        raw, _ = make_state("Surge XT", cand["surge"])
        rel = f"vst/{music_name} - extraits/s{int(sample):02d}-{k}.bin"
        vst.state_path(rel).parent.mkdir(parents=True, exist_ok=True)
        vst.state_path(rel).write_bytes(raw)
        keep = {key: base[key] for key in ("name", "velocity", "reverb", "pan", "gain_db") if key in base}
        out["samples"][sample] = {**keep, "vsti": {"plugin": "Surge XT", "state": rel, "bend_range": BEND,
                                                    "preset": cand["surge"]}}
    elif "remplace" in cand:
        out["samples"][sample] = copy.deepcopy(cand["remplace"])
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    music = pathlib.Path(sys.argv[1])
    m = open_music(music)
    plan = json.loads((ROOT / "songs" / "extraits" / f"{m.name}.json").read_text(encoding="utf-8"))
    length = float(plan.get("duree", 20))
    cfg = render.load_config(m.cfg_path)
    default_sf = cfg.get("soundfont", "GeneralUser-GS.sf2")
    master = cfg.get("master", {})
    stem_dir = m.out_dir / "stems"
    cache = stem_dir / "extraits"
    cache.mkdir(parents=True, exist_ok=True)
    dest = m.out_dir / "extraits"
    dest.mkdir(parents=True, exist_ok=True)

    print("Pistes du remaster actuel (déjà rendues : relues)…", flush=True)
    rts = render.routes(m.song, m.mod, cfg)
    stems = []
    for sample, ch, inst, ev in rts:
        name = f"s{sample:02d}-v{ch + 1}{inst.part}"
        a = render.render_part(name, ev, inst, m.song.duration, stem_dir, default_sf,
                               seed=sample * 10 + ch + (500 if inst.part == "D" else 0))
        stems.append((a, inst, ch, 1.0))
    if master.get("balance", "original") == "original":
        stems = render.balance_on_original(stems, rts, m.song, m.mod)

    for sample, spec in plan["samples"].items():
        s = int(sample)
        times = [t for r in rts if r[0] == s for t, msg in r[3] if msg.type == "note_on" and msg.velocity]
        start = float(spec["debut"]) if spec.get("debut") is not None else busiest_start(times, length)
        w0 = max(0.0, start - PRE)
        print(f"\n{spec['titre']} (sample {s}) : passage de {start:.1f} s à {start + length:.1f} s", flush=True)
        others = [(window(a, w0, length + PRE), inst, ch, g)
                  for (a, inst, ch, g), r in zip(stems, rts) if r[0] != s]
        current = [(window(a, w0, length + PRE), inst, ch, g)
                   for (a, inst, ch, g), r in zip(stems, rts) if r[0] == s]
        e_cur = energy(current)
        for k, cand in enumerate(spec["candidats"]):
            if k == 0:
                mine = current
            else:
                cfg_k = candidate_cfg(cfg, sample, cand, m.name, k)
                mine = []
                for smp, ch, inst, ev in render.routes(m.song, m.mod, cfg_k):
                    if smp != s:
                        continue
                    a = render.render_part(f"x{s:02d}-{k}-v{ch + 1}{inst.part}", excerpt(ev, w0, length + PRE),
                                           inst, length + PRE, cache, default_sf,
                                           seed=s * 10 + ch + (500 if inst.part == "D" else 0))
                    mine.append((window(a, 0.0, length + PRE), inst, ch, 1.0))
                e = energy(mine)
                g = float(np.sqrt(e_cur / e)) if e > 0 and e_cur > 0 else 1.0  # même niveau que le son actuel
                mine = [(a, inst, ch, gg * g) for a, inst, ch, gg in mine]
            out = render.mix(others + mine, master)[:, int(PRE * SR):]
            fade = np.ones(out.shape[1], np.float32)
            nf = min(out.shape[1], SR)
            fade[-nf:] = np.linspace(1, 0, nf)
            out = out * fade
            safe = "".join(c if c not in '<>:"/\\|?*' else "-" for c in cand["nom"])
            mp3 = dest / f"{spec['titre']} {k} - {safe}.mp3"
            wav = dest / "extrait.wav"
            sf.write(wav, out.T, SR, subtype="FLOAT")
            render.to_mp3(wav, mp3, {"title": f"{spec['titre']} {k} - {cand['nom']}", "album": m.name},
                          master.get("loudness", -14.0))
            wav.unlink()
            print(f"  {k} : {cand['nom']}", flush=True)
    print(f"\n→ {dest}")


if __name__ == "__main__":
    main()
