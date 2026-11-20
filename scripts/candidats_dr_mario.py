"""Lancer depuis le dossier du projet : .venv\Scripts\python scripts\candidats_dr_mario.py

Écrit songs/extraits/Dr Mario.json : série 2 (20/11/2026), d'après le retour de l'utilisateur :
batterie rock / métal, guitare rythmique néo-métal lourde mais nette, lead heavy métal percutant et sec, chœur naturel."""
import copy, json, pathlib

cfg = json.loads(pathlib.Path("songs/Dr Mario.json").read_text(encoding="utf-8"))
S = cfg["samples"]

# ---------------------------------------------------------------- batterie
KITS = {
    "SM Drums": ("sm-drums", "Programs/SM_Drums_kit.sfz", 36, 38, 42, 57),
    "Muldjord Kit": ("muldjord-kit", "DrumGizmo/MuldjordKit/Stereo/DrumGizmo MuldjordKit.sfz", 36, 38, 42, 49),
    "Naked Drums": ("naked-drums", "Wilkinson Audio/Naked Drums/User/Naked Drums GM.sfz", 36, 38, 42, 49),
    "Sonor (Sam's)": ("sams-sonor", "SamsSonor.sfz", 36, 38, 42, 49),
}
PUNCH_K = [{"type": "HighpassFilter", "cutoff_frequency_hz": 30},
           {"type": "PeakFilter", "cutoff_frequency_hz": 60, "gain_db": 3, "q": 1.0},
           {"type": "PeakFilter", "cutoff_frequency_hz": 350, "gain_db": -5, "q": 1.0},
           {"type": "PeakFilter", "cutoff_frequency_hz": 4000, "gain_db": 5, "q": 1.0},
           {"type": "Compressor", "threshold_db": -18, "ratio": 4, "attack_ms": 10, "release_ms": 100}]
PUNCH_S = [{"type": "HighpassFilter", "cutoff_frequency_hz": 80},
           {"type": "PeakFilter", "cutoff_frequency_hz": 200, "gain_db": 3, "q": 1.0},
           {"type": "PeakFilter", "cutoff_frequency_hz": 5000, "gain_db": 3, "q": 1.0},
           {"type": "Compressor", "threshold_db": -16, "ratio": 4, "attack_ms": 5, "release_ms": 80}]


def kit(name, punch):
    bank, prog, k, s, h, c = KITS[name]
    sfz = {"bank": bank, "program": prog}
    samples = {
        "1": {"name": "Grosse caisse", "drum": k, "velocity": 118, "reverb": 0.0, "pan": 0, "sfz": sfz,
              "fx": copy.deepcopy(PUNCH_K) if punch else [], "gain_db": S["1"].get("gain_db", 0)},
        "2": {"name": "Caisse claire", "drum": s, "velocity": 112, "reverb": 0.12, "pan": 0, "sfz": sfz,
              "fx": copy.deepcopy(PUNCH_S) if punch else []},
    }
    ex = copy.deepcopy(cfg["extras"])
    ex["hihat"].update({"note": h, "sfz": sfz})
    ex["crash"].update({"note": c, "sfz": sfz})
    return {"nom": f"{name}{', son rock compressé' if punch else ''}", "samples": samples, "extras": ex}


drums = [{"nom": "actuel (Big Rusty Drums)"}]
for name in KITS:
    drums.append(kit(name, False))
for name in KITS:
    drums.append(kit(name, True))

# ---------------------------------------------------------------- guitares
def chain(model, cab, input_db=0.0, tight=True, extra=None):
    fx = [{"type": "HighpassFilter", "cutoff_frequency_hz": 120 if tight else 100}]
    if tight:  # le grave qui « bave » est coupé avant l'ampli, comme une pédale overdrive devant un ampli métal
        fx.append({"type": "PeakFilter", "cutoff_frequency_hz": 800, "gain_db": 3, "q": 0.7})
    fx.append({"type": "nam", "model": model, **({"input_db": input_db} if input_db else {})})
    if tight:
        fx.append({"type": "NoiseGate", "threshold_db": -48, "ratio": 10, "attack_ms": 1, "release_ms": 60})
    fx += [{"type": "cab", "ir": cab},
           {"type": "HighpassFilter", "cutoff_frequency_hz": 80},
           {"type": "PeakFilter", "cutoff_frequency_hz": 400, "gain_db": -2, "q": 1.0},
           {"type": "LowpassFilter", "cutoff_frequency_hz": 9000}]
    return fx + (extra or [])


AMPS = {
    "5150 boosté": "Helga B 5150 BlockLetter - Boosted",
    "6505+ canal rouge + MXR": "Helga B 6505+ Red ch - MXR Drive V2",
    "Engl Savage": "Tom C Axe FX 2 Engl Savage",
    "Engl E530 + DS-1": "Tom C Engl e530 preamp & 840 power amp with Boss DS1 Overdrive",
    "Fortin Grind": "Tudor N Fortin Grind Mini Knob @ 5 ESR_0.0012_lite",
    "5150 sans boost": "Helga B 5150 BlockLetter - NoBoost",
    "6505+ canal rouge": "Helga B 6505+ Red Ch - NoBoost rock",
}


def rhythm(amp_label, cab="16-nacho-guacamole", input_db=0.0):
    model = AMPS[amp_label]
    out = {}
    for s in ("11", "12"):
        b = copy.deepcopy(S[s])
        b["fx"] = chain(model, cab, input_db)
        b["double"]["fx"] = chain(model, cab, input_db)
        b["double"]["delay_ms"] = 0
        b.pop("comment", None)
        out[s] = b
    label = f"{amp_label}{', baffle ' + cab.split('-', 1)[1] if cab != '16-nacho-guacamole' else ''}"
    label += ", moins de gain" if input_db < 0 else ""
    return {"nom": f"deux guitares, {label}, son serré", "samples": out}


rhythm_c = [{"nom": "actuel (Engl Savage à gauche, 6505+ à droite)"},
            rhythm("5150 boosté"), rhythm("6505+ canal rouge + MXR"), rhythm("Engl Savage"),
            rhythm("Engl E530 + DS-1"), rhythm("Fortin Grind"), rhythm("5150 boosté", "01-cookie-monster"),
            rhythm("6505+ canal rouge + MXR", input_db=-6), rhythm("5150 sans boost"), rhythm("6505+ canal rouge")]


def lead(amp_label, guitar="Programs/04-green_twang.sfz", gname="guitare green", model=None):
    b = copy.deepcopy(S["5"])
    b["sfz"] = {"bank": "black-and-green-guitars", "program": guitar}
    b["fx"] = chain(model or AMPS[amp_label], "18-wasabi-warrior", tight=True,
                    extra=[{"type": "Compressor", "threshold_db": -14, "ratio": 3, "attack_ms": 12, "release_ms": 80}])
    b["reverb"] = 0.05
    b.pop("comment", None)
    return {"nom": f"{gname}, {amp_label}, sec (sans écho)", "samples": {"5": b}}


lead_c = [{"nom": "actuel (5152 Lead + TS9, écho léger)"},
          lead("5152 Lead + TS9", model="Tim R 5152 Lead + TS9"),
          lead("5150 boosté"), lead("5150 boosté", "Programs/07-black_twang.sfz", "guitare black"),
          lead("6505+ canal rouge + MXR"), lead("Engl Savage"), lead("Fortin Grind"),
          lead("Engl E530 + DS-1", "Programs/07-black_twang.sfz", "guitare black"),
          lead("Mesa Mark IV", model="Roman A LT_MESA_MARKIV_1"),
          lead("5150 boosté", "Programs/10-combo_twang.sfz", "deux micros")]

# ---------------------------------------------------------------- chœur
def choir(nom, base, double=None):
    b = {"name": "Chœur", "velocity": 90, "reverb": 0.35, **base}
    if double:
        b["double"] = {"width": 0.6, "delay_ms": 0, **double}
    return {"nom": nom, "samples": {"10": b}}


# La banque « Discord SFZ GM » n'a pas de vrai chœur (fichier « dummy » : une sinusoïde) : pas retenue.
choir_c = [{"nom": "actuel (chœur General MIDI)"},
           choir("chœur General MIDI, banque MuseScore", {"program": 52, "soundfont": "MuseScore_General.sf3"}),
           choir("chœur General MIDI, une octave plus haut", {"program": 52, "transpose": 12}),
           choir("voix « Ooh » General MIDI, plus de réverbération", {"program": 53, "reverb": 0.5})]

plan = {"duree": 20, "parties": [
    {"titre": "Batterie", "samples": ["1", "2"], "candidats": drums},
    {"titre": "Guitare rythmique", "samples": ["11", "12"], "candidats": rhythm_c},
    {"titre": "Lead", "samples": ["5"], "candidats": lead_c},
    {"titre": "Chœur", "samples": ["10"], "candidats": choir_c},
]}
pathlib.Path("songs/extraits/Dr Mario.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1) + "\n",
                                                         encoding="utf-8")
print({p["titre"]: len(p["candidats"]) for p in plan["parties"]})
