"""Lancer depuis le dossier du projet (21/11/2026), puis scripts/production_metal.py "in/music/Lotus/Lotus - title.mod" batterie=11,12 basse=13 rythmique=2,14.

Fiche de Lotus - title : rôles corrigés, sons de Dr Mario (choisis à l'écoute), parties des partitions."""
import copy, json, pathlib, shutil, sys
sys.path.insert(0, ".")
from remaster import modfile, analyze

p = pathlib.Path("songs/Lotus - title.json")
backup = p.with_name("Lotus - title (avant métal).json")
if not backup.exists():
    shutil.copy2(p, backup)
cfg = json.loads(p.read_text(encoding="utf-8"))
dm = json.loads(pathlib.Path("songs/Dr Mario.json").read_text(encoding="utf-8"))
D = dm["samples"]
mod = modfile.load("in/music/Lotus/Lotus - title.mod")
root14 = round(analyze.root_midi(mod.samples[13]) + 12, 2)  # les deux notes du power chord trompent la détection

kick, snare = copy.deepcopy(D["1"]), copy.deepcopy(D["2"])
for s, note in ((kick, 36), (snare, 38)):
    s["drum"] = note
    s["comment"] = "son de Dr Mario choisi à l'écoute : Naked Drums, son rock compressé"
lead = copy.deepcopy(D["12"])  # power chords : les guitares rythmiques de Dr Mario (6505+ serré)
lead.update({"name": "Guitare 1 (power chords)", "comment": "sample 2 : la quinte est dans le son (power chord) ; "
             "mélodie en power chords, guitares et ampli de la rythmique de Dr Mario"})
chug = copy.deepcopy(D["11"])
chug.update({"name": "Guitare 2 (étouffée)", "root": root14, "comment": "sample 14 : power chord grave et court "
             "(étouffé) ; la détection prenait la fondamentale manquante, une octave trop bas : root corrigée"})
bass = copy.deepcopy(D["3"])
bass.update({"name": "Basse", "comment": "sample 13 : la basse (la fiche automatique l'avait prise pour la mélodie)"})
cfg["samples"] = {
    "2": lead, "11": kick, "12": snare, "13": bass, "14": chug,
    "7": {"name": "Ignoré", "mute": True, "comment": "2 notes seulement"},
}
for s in cfg["samples"].values():
    s.pop("humanize", None)  # remis par production_metal.py
cfg["extras"] = copy.deepcopy(dm["extras"])
cfg["master"] = copy.deepcopy(dm["master"])
cfg["comment"] = ("rôles corrigés le 21/11/2026 (Claude, d'après le son des samples) ; sons de Dr Mario choisis à "
                  "l'écoute par l'utilisateur, puis production métal")
cfg["partitions"] = {
    "Guitare 1 (power chords)": {"instrument": "guitare", "samples": [2], "lead": True,
                                 "comment": "la mélodie en power chords (sample 2)"},
    "Guitare 2 (étouffée)": {"instrument": "guitare", "samples": [14], "comment": "power chords graves étouffés"},
    "Basse": {"instrument": "basse", "samples": [13]},
    "Batterie (version enrichie)": {"instrument": "batterie", "samples": [11, 12], "extras": True},
}
cfg["piano"].update({"melody": "Guitare 1 (power chords)", "bass": [13], "harmony": [2, 13, 14]})
p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("root 14 :", root14, "→", analyze.note_name(root14))
