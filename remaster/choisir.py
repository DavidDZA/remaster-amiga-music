"""Choisir à l'oreille le son d'un sample dans un VST : python -m remaster.choisir <musique> --sample N --vst NOM

La fenêtre du VST s'ouvre ; pendant ce temps, les notes que joue ce sample dans la musique passent en boucle dans le
VST, vers les haut-parleurs (un extrait de 20 s) : on change de preset, on l'entend aussitôt. On ferme la fenêtre
quand le son plaît : l'état du VST est enregistré dans songs/vst/<musique>/ et la fiche songs/<musique>.json est
mise à jour (clé « vsti »). Il reste à relancer le remaster : python -m remaster <musique>.

    python -m remaster.choisir <musique>                    les samples de la musique, et ce qui les joue
    python -m remaster.choisir <musique> --sample 5         la liste des instruments VST, puis le choix
    python -m remaster.choisir <musique> --sample 5 --vst "Surge XT" --debut 30
    python -m remaster.choisir <musique> --sample 5 --effet "Surge XT Effects"   un effet VST sur cette piste

Pour une musique autre que .mod : --sous-morceau N, comme pour python -m remaster.
"""
from __future__ import annotations
import argparse
import json
import pathlib
import sys
import tempfile
import numpy as np
from . import render, midi, vst
from .__main__ import open_music


def tracks_of(rts, sample: int):
    """Les pistes (sample, voie) d'un sample, sans la deuxième prise d'une partie doublée."""
    return [r for r in rts if r[0] == sample and r[2].part != "D"]


def excerpt(events, start: float, length: float):
    """Les événements de [start, start + length[, ramenés à 0 ; le pitch bend et le volume en cours à `start`
    sont rejoués au début."""
    state = {}
    out = []
    for t, m in sorted(events, key=lambda e: e[0]):
        if t < start:
            if m.type == "pitchwheel":
                state["bend"] = m
            elif m.type == "control_change" and m.control == 11:
                state["expr"] = m
            continue
        if t >= start + length:
            break
        out.append((t - start, m))
    return [(0.0, m) for m in state.values()] + out


def describe(cfg: dict, sample: int) -> str:
    s = cfg.get("samples", {}).get(str(sample), {})
    if s.get("vsti"):
        return f"VST {s['vsti']['plugin']}"
    if s.get("sfz"):
        return f"banque SFZ {s['sfz']['bank']}"
    if s.get("drum") is not None:
        return f"batterie GM, note {s['drum']}"
    return f"SoundFont, programme GM {s.get('program', 0)}"


def pick(names: list[str], what: str) -> str:
    print(f"\n{what} :")
    for i, n in enumerate(names, 1):
        print(f"  {i:2d}. {n}")
    if not sys.stdin.isatty():
        raise SystemExit("\nRelancer avec --vst \"<nom>\" (ou --effet \"<nom>\").")
    while True:
        r = input("Numéro : ").strip()
        if r.isdigit() and 1 <= int(r) <= len(names):
            return names[int(r) - 1]


def to_rate(audio: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    if sr_from == sr_to:
        return audio
    from scipy.signal import resample_poly
    from math import gcd
    g = gcd(sr_from, sr_to)
    return resample_poly(audio, sr_to // g, sr_from // g, axis=1).astype(np.float32)


def save(cfg_path: pathlib.Path, cfg: dict, plug, music_name: str, filename: str) -> str:
    rel = f"vst/{music_name}/{filename}"
    p = vst.state_path(rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(plug.raw_state)
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return rel


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Choisir à l'oreille, dans un VST, le son d'un sample d'une musique.")
    ap.add_argument("musique", type=pathlib.Path)
    ap.add_argument("--sample", type=int, help="n° du sample (sans lui : la liste des samples)")
    ap.add_argument("--vst", help="instrument VST3 (sans lui : la liste, ou celui déjà choisi)")
    ap.add_argument("--effet", help="un effet VST3 à ajouter à la fin de la chaîne d'effets de ce sample")
    ap.add_argument("--debut", type=float, help="début de l'extrait (s) ; par défaut la première note du sample")
    ap.add_argument("--duree", type=float, default=20.0, help="longueur de l'extrait en boucle (s), 20 par défaut")
    ap.add_argument("--bend", type=float, help="amplitude du pitch bend du synthé (demi-tons), 2 par défaut")
    ap.add_argument("--volume", type=float, default=0.5, help="volume d'écoute (0 à 1), 0,5 par défaut")
    ap.add_argument("--sous-morceau", type=int)
    ap.add_argument("--max", type=int, default=300)
    a = ap.parse_args()

    m = open_music(a.musique, a.sous_morceau, a.max)
    cfg = render.load_config(m.cfg_path)
    rts = render.routes(m.song, m.mod, cfg)
    if a.sample is None:
        print(f"\nSamples de « {m.name} » (fiche : {m.cfg_path}) :")
        for s in sorted({r[0] for r in rts}):
            evs = [t for r in tracks_of(rts, s) for t, msg in r[3] if msg.type == "note_on" and msg.velocity]
            name = m.mod.samples[s - 1].name.strip() or "sans nom"
            print(f"  {s:2d}. {name:24s} {len(evs):5d} notes, dès {min(evs):6.1f} s   joué par : {describe(cfg, s)}")
        print("\nPuis : python -m remaster.choisir <musique> --sample N")
        return
    mine = tracks_of(rts, a.sample)
    if not mine:
        raise SystemExit(f"Le sample {a.sample} ne joue pas (ou il est coupé : « mute » dans la fiche).")
    events = [e for r in mine for e in r[3]]
    first = min(t for t, msg in events if msg.type == "note_on")
    start = first if a.debut is None else a.debut
    part = excerpt(events, start, a.duree)
    if not any(msg.type == "note_on" for _, msg in part):
        raise SystemExit(f"Aucune note du sample {a.sample} entre {start:.0f} s et {start + a.duree:.0f} s.")

    sample_cfg = cfg.setdefault("samples", {}).setdefault(str(a.sample), {})
    print(f"Catalogue des VST… (un VST qui plante est mis de côté)")
    cat = vst.catalogue()
    if a.effet:
        choose_effect(a, m, cfg, sample_cfg, mine, part, cat)
        return
    instruments = sorted((k for k, v in cat.items() if v.get("ok") and v.get("instrument")), key=str.lower)
    current = sample_cfg.get("vsti") or {}
    name = a.vst or current.get("plugin") or pick(instruments, "Instruments VST")
    if name not in cat or not cat[name].get("ok"):
        raise SystemExit(f"VST inutilisable ou absent : {name} ; instruments : {', '.join(instruments)}")
    spec = {"plugin": name, "bend_range": a.bend or (current.get("bend_range", 2) if current.get("plugin") == name
                                                    else 2)}
    if current.get("plugin") == name and current.get("state"):
        spec["state"] = current["state"]  # on repart du son déjà choisi
    plug = vst.prepare(spec)
    print(f"\nFenêtre de {name} : choisir un preset en écoutant ({a.duree:.0f} s en boucle dès {start:.0f} s).")
    print("Fermer la fenêtre quand le son plaît.")
    vst.listen_while_editing(plug, events=part, spec=spec, source_bend_range=midi.BEND_RANGE, volume=a.volume)
    if sys.stdin.isatty() and input("Garder ce son ? [O/n] ").strip().lower().startswith("n"):
        print("Rien n'est changé.")
        return
    spec.pop("state", None)
    sample_cfg["vsti"] = {"plugin": name, "state": f"vst/{m.name}/s{a.sample:02d}.bin", **spec}
    rel = save(m.cfg_path, cfg, plug, m.name, f"s{a.sample:02d}.bin")
    print(f"Enregistré : songs/{rel}, et « vsti » du sample {a.sample} dans {m.cfg_path.name}.")
    print(f"Ensuite : python -m remaster \"{a.musique}\"")


def choose_effect(a, m, cfg, sample_cfg, mine, part, cat):
    effects = sorted((k for k, v in cat.items() if v.get("ok") and not v.get("instrument")), key=str.lower)
    name = a.effet
    if name not in cat or not cat[name].get("ok") or cat[name].get("instrument"):
        raise SystemExit(f"Effet VST inutilisable ou absent : {name} ; effets : {', '.join(effects)}")
    chain = [f for f in sample_cfg.get("fx", []) if not (f.get("type") == "vst" and f.get("plugin") == name)]
    old = next((f for f in sample_cfg.get("fx", []) if f.get("type") == "vst" and f.get("plugin") == name), {})
    # l'extrait joué par l'instrument actuel et ses effets (sans celui qu'on choisit)
    _, ch, inst, _ = mine[0]
    inst = render.dataclasses.replace(inst, fx=chain)
    print("Rendu de l'extrait avec l'instrument actuel…")
    with tempfile.TemporaryDirectory() as tmp:
        audio = render.render_part("extrait", part, inst, a.duree, pathlib.Path(tmp),
                                   cfg.get("soundfont", "GeneralUser-GS.sf2"))
    peak = float(np.max(np.abs(audio))) or 1.0
    audio = audio / peak * 0.5
    spec = {"plugin": name, **({"state": old["state"]} if old.get("state") else {})}
    plug = vst.prepare(spec)
    with vst.output_stream() as stream:
        sr = int(stream.sample_rate)
    audio = to_rate(audio, render.SR, sr)
    print(f"\nFenêtre de {name} : régler l'effet en écoutant ({a.duree:.0f} s en boucle). Fermer quand ça plaît.")
    vst.listen_while_editing(plug, audio=audio, volume=a.volume)
    if sys.stdin.isatty() and input("Garder cet effet ? [O/n] ").strip().lower().startswith("n"):
        print("Rien n'est changé.")
        return
    safe = "".join(c if c.isalnum() else "_" for c in name)
    fname = f"s{a.sample:02d}-{safe}.bin"
    sample_cfg["fx"] = chain + [{"type": "vst", "plugin": name, "state": f"vst/{m.name}/{fname}"}]
    rel = save(m.cfg_path, cfg, plug, m.name, fname)
    print(f"Enregistré : songs/{rel}, ajouté à la fin des effets du sample {a.sample}.")


if __name__ == "__main__":
    main()
