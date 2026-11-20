"""Une liste d'extraits à écouter pour choisir un son : le même passage de la musique, dans le mix complet (version
enrichie : avec le charleston et les crashs ajoutés), avec à chaque fois un autre son pour une partie (un sample, ou
plusieurs ensemble : grosse caisse + caisse claire, les deux guitares rythmiques…). L'utilisateur écoute et donne
un numéro.

    .venv\\Scripts\\python scripts\\extraits.py "in\\music\\Dr Mario\\Dr Mario.mod" [partie…]

Les candidats sont dans songs\\extraits\\<musique>.json :
    {"duree": 20, "parties": [{"titre": "Batterie", "samples": ["1", "2"], "debut": 40 (facultatif),
        "candidats": [
            {"nom": "actuel …"},                               le son de la fiche, tel quel (toujours le n° 0)
            {"nom": "…", "samples": {"1": {…}, "2": {…}},      les réglages de ces samples (fiche complète)
                         "extras": {…}},                       et ceux du charleston / des crashs ajoutés
            {"nom": "…", "nam": "<ampli NAM>"},                la fiche, avec un autre ampli (tous les samples)
            {"nom": "…", "surge": "Leads/Classic Lead 1"},     un preset de Surge XT
        ]}]}

Résultat : out\\Retravaillées\\<musique>\\extraits\\<titre> <n> - <nom>.mp3. Chaque candidat est mis au niveau du son
actuel sur ce passage : seul le son change, pas le volume. Le passage : les 20 s où la partie joue le plus de notes.
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
from remaster import render, reference, vst, extras  # noqa: E402
from remaster.__main__ import open_music  # noqa: E402
from remaster.choisir import excerpt  # noqa: E402

SR = render.SR
PRE = 1.0  # seconde jouée avant le passage (attaques, réverbération), coupée ensuite


def busiest_start(times: list[float], length: float) -> float:
    """L'attaque à partir de laquelle la partie joue le plus de notes en `length` secondes."""
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


def seed_of(sample: int, ch: int, part: str) -> int:
    return sample * 10 + ch + (500 if part == "D" else 0)


def candidate_cfg(cfg: dict, samples: list[str], cand: dict, music_name: str, tag: str) -> dict:
    out = copy.deepcopy(cfg)
    for s in samples:
        base = out["samples"][s]
        if "samples" in cand and s in cand["samples"]:
            out["samples"][s] = copy.deepcopy(cand["samples"][s])
        elif "nam" in cand:
            for chain in [base.get("fx", [])] + ([base["double"].get("fx", [])] if base.get("double") else []):
                for f in chain:
                    if f.get("type") == "nam":
                        f["model"] = cand["nam"]
        elif "surge" in cand:
            from essai_vst import make_state, BEND
            raw, _ = make_state("Surge XT", cand["surge"])
            rel = f"vst/{music_name} - extraits/s{int(s):02d}-{tag}.bin"
            vst.state_path(rel).parent.mkdir(parents=True, exist_ok=True)
            vst.state_path(rel).write_bytes(raw)
            keep = {k: base[k] for k in ("name", "velocity", "reverb", "pan", "gain_db") if k in base}
            out["samples"][s] = {**keep, "vsti": {"plugin": "Surge XT", "state": rel, "bend_range": BEND,
                                                  "preset": cand["surge"]}}
    if "extras" in cand:
        out["extras"] = copy.deepcopy(cand["extras"])
    return out


def extra_stems(song, mod, cfg, drum_stems, drum_events, w0, length, cache, default_sf, tag):
    """Le charleston et les crashs ajoutés, sur le passage, au niveau d'un coup de la batterie (comme le remaster)."""
    if not cfg.get("extras"):
        return []
    drum_samples = {s for s, inst in ((int(k), v) for k, v in cfg["samples"].items()) if inst.get("drum") is not None}
    hit = render.per_hit_energy([(a, g, ev) for (a, _, _, g), ev in zip(drum_stems, drum_events)])
    out = []
    for name, inst, ev in extras.extra_parts(song, mod, drum_samples, cfg["extras"]):
        evw = excerpt(ev, w0, length)
        if not evw:
            continue
        a = window(render.render_part(f"{name}-{tag}", evw, inst, length, cache, default_sf, seed=999), 0, length)
        own = render.per_hit_energy([(a, 1.0, evw)])
        out.append((a, inst, 0, float(np.sqrt(hit / own)) if hit and own else 1.0))
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    music = pathlib.Path(sys.argv[1])
    only = set(sys.argv[2:])
    m = open_music(music)
    plan = json.loads((ROOT / "songs" / "extraits" / f"{m.name}.json").read_text(encoding="utf-8"))
    length = float(plan.get("duree", 20))
    span = length + PRE
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
        a = render.render_part(f"s{sample:02d}-v{ch + 1}{inst.part}", ev, inst, m.song.duration, stem_dir,
                               default_sf, seed=seed_of(sample, ch, inst.part))
        stems.append((a, inst, ch, 1.0))
    if master.get("balance", "original") == "original":
        stems = render.balance_on_original(stems, rts, m.song, m.mod)

    for part in plan["parties"]:
        if only and part["titre"] not in only:
            continue
        samples = [str(s) for s in part["samples"]]
        mine_ids = {int(s) for s in samples}
        is_drums = any(cfg["samples"][s].get("drum") is not None for s in samples)
        times = [t for r in rts if r[0] in mine_ids for t, msg in r[3] if msg.type == "note_on" and msg.velocity]
        start = float(part["debut"]) if part.get("debut") is not None else busiest_start(times, length)
        w0 = max(0.0, start - PRE)
        print(f"\n{part['titre']} (samples {', '.join(samples)}) : de {start:.1f} s à {start + length:.1f} s", flush=True)
        win = [(window(a, w0, span), inst, ch, g) for a, inst, ch, g in stems]
        others = [st for st, r in zip(win, rts) if r[0] not in mine_ids]
        current = [st for st, r in zip(win, rts) if r[0] in mine_ids]
        drum_now = [(st, excerpt(r[3], w0, span)) for st, r in zip(win, rts) if r[2].drum is not None]
        e_cur = energy(current)
        for k, cand in enumerate(part["candidats"]):
            tag = f"{part['titre'][:3].lower()}{k}"
            if k == 0:
                mine = current
                cfg_k = cfg
                drums = drum_now
            else:
                cfg_k = candidate_cfg(cfg, samples, cand, m.name, tag)
                mine, mine_ev = [], []
                for smp, ch, inst, ev in render.routes(m.song, m.mod, cfg_k):
                    if smp not in mine_ids:
                        continue
                    evw = excerpt(ev, w0, span)
                    a = render.render_part(f"x{smp:02d}-{tag}-v{ch + 1}{inst.part}", evw, inst, span, cache,
                                           default_sf, seed=seed_of(smp, ch, inst.part))
                    mine.append((window(a, 0.0, span), inst, ch, 1.0))
                    mine_ev.append((inst, evw))
                e = energy(mine)
                g = float(np.sqrt(e_cur / e)) if e > 0 and e_cur > 0 else 1.0  # même niveau que le son actuel
                mine = [(a, inst, ch, gg * g) for a, inst, ch, gg in mine]
                if is_drums:
                    drums = [(st, ev) for st, (inst, ev) in zip(mine, mine_ev) if inst.drum is not None]
                else:
                    drums = drum_now
            added = extra_stems(m.song, m.mod, cfg_k, [d for d, _ in drums], [ev for _, ev in drums],
                                w0, span, cache, default_sf, tag if (k and is_drums) else "actuel")
            out = render.mix(others + mine + added, master)[:, int(PRE * SR):]
            nf = min(out.shape[1], SR)
            out[:, -nf:] *= np.linspace(1, 0, nf, dtype=np.float32)
            safe = "".join(c if c not in '<>:"/\\|?*' else "-" for c in cand["nom"])
            mp3 = dest / f"{part['titre']} {k} - {safe}.mp3"
            wav = dest / "extrait.wav"
            sf.write(wav, out.T, SR, subtype="FLOAT")
            render.to_mp3(wav, mp3, {"title": f"{part['titre']} {k} - {cand['nom']}", "album": m.name},
                          master.get("loudness", -14.0))
            wav.unlink()
            print(f"  {k} : {cand['nom']}", flush=True)
    print(f"\n→ {dest}")


if __name__ == "__main__":
    main()
