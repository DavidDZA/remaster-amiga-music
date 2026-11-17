# Remaster AMIGA Music

Un module Amiga (`.mod` ProTracker) rejoué avec des **instruments modernes**, puis mixé et enregistré en **MP3**.
Tout est gratuit et tourne sur le PC, sans rien installer dans Windows : les outils sont dans le dossier du projet.

Prototype en ligne de commande (17/11/2026), avant une éventuelle vraie appli PC.

## Le principe

Un `.mod`, ce n'est pas un enregistrement : c'est une partition (patterns, 4 voies) plus de petits samples 8 bits.
On peut donc garder la partition et **changer les instruments** :

1. **Lecture du module** (`remaster/modfile.py`) : samples, patterns, ordre.
2. **Rejeu tick par tick comme ProTracker** (`remaster/player.py`) : tempo, vitesse, glissandos (1xx, 2xx, 3xx),
   vibrato, arpèges, volumes, sauts. Pour chaque voie et chaque tick : quel sample, quelle hauteur, quel volume.
   La durée obtenue est celle d'OpenMPT (6 min 10 s pour *Dr Mario*).
3. **Hauteur de chaque sample** (`remaster/analyze.py`) : un sample n'est pas forcément accordé en do ; son spectre
   donne la note qu'il joue (la basse de *Dr Mario* est accordée en sol#).
4. **Vers le MIDI** (`remaster/midi.py`) : une piste par couple (sample, voie), monophonique comme l'Amiga ; les
   glissandos et le vibrato deviennent du *pitch bend* (amplitude ±24 demi-tons), le volume du CC 11. Une note peut
   devenir un accord (power chord `[0, 7, 12]` pour une guitare saturée).
5. **Rendu** (`remaster/render.py`) : chaque piste est jouée par **FluidSynth** avec une **SoundFont** (banque
   d'instruments) gratuite, puis mixée : panoramique, réverbération, compression, limiteur, niveau −14 LUFS,
   MP3 320 kbit/s CBR.
6. **Équilibrage sur l'original** (`remaster/reference.py`) : chaque nouvel instrument prend dans le mix la même place
   que son sample dans le module (sinon une guitare saturée écrase tout et la mélodie disparaît). `gain_db` dans la
   fiche ne sert plus qu'aux retouches.
7. **Version enrichie** (`remaster/extras.py`) : avec 4 voies, les musiciens gardaient souvent grosse caisse et caisse
   claire. On ajoute un **charleston** (toutes les 2 lignes, accentué sur les temps) et des **crashs** (début de chaque
   nouvelle partie, retour de la batterie après une pause), là où la batterie joue.

## Utilisation

```sh
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python scripts\setup_tools.py        # FluidSynth, OpenMPT, 2 SoundFonts (≈ 80 Mo, une fois)
.venv\Scripts\python -m remaster "Dr Mario.mod"
```

Dans `out\Dr Mario\` :

| Fichier | Contenu |
|---|---|
| `Dr Mario (original).mp3` | le module tel quel (rendu OpenMPT), pour comparer |
| `Dr Mario (remaster fidèle).mp3` | mêmes notes, nouveaux instruments |
| `Dr Mario (remaster enrichi).mp3` | pareil + charleston et crashs ajoutés |
| `Dr Mario (remaster).mid` | la partition en MIDI, pour la reprendre dans un logiciel de musique |
| `samples\` | les samples d'origine en WAV, pour les écouter |
| `stems\` | chaque piste séparée (MIDI et WAV) |

Pour un autre module, la première fois, une **fiche d'instruments** `songs\<nom>.json` est créée (un piano pour
tout) : à compléter, puis relancer.

### La fiche d'instruments (`songs\Dr Mario.json`)

Pour chaque sample (`"1"` à `"31"`) :

| Clé | Rôle |
|---|---|
| `program` | instrument General MIDI (0 piano, 30 guitare saturée, 33/34 basse, 52 chœur…) |
| `drum` | ou bien un son de batterie (note GM : 36 grosse caisse, 38 caisse claire, 42 charleston, 49 crash) |
| `drum_kit` | kit de batterie (0 Standard, 16 Power, 25 TR-808…) |
| `chord` | notes ajoutées (demi-tons) : `[0, 7, 12]` power chord |
| `transpose` | décalage en demi-tons (−12 : une octave plus bas) |
| `root` | note MIDI du sample au C-2, si la détection automatique se trompe |
| `max_length` | coupe les notes (secondes) : utile pour un son étouffé |
| `velocity`, `gain_db`, `pan`, `reverb` | force de frappe, volume, panoramique (−1 à 1, ou par voie), réverbération |
| `soundfont` | une autre SoundFont pour cet instrument |
| `mute` | ne pas jouer ce sample |

`extras` règle les ajouts de la version enrichie (`gain_db` : tant de dB sous un coup de la batterie d'origine).

### Instruments retenus pour *Dr Mario*

Les noms des samples sont des messages (« composed by betrayer », « greets to tokyo kid »…) : les instruments ont
été reconnus à l'analyse du son et de leur rôle dans les patterns.

| Sample | Ce que c'est | Remplacé par |
|---|---|---|
| 1, 2 | grosse caisse, caisse claire | kit Power |
| 3 | basse (accordée en sol#) | Picked Bass |
| 5 | lead avec bends | Distortion Guitar |
| 10 | chœur | Choir Aahs |
| 11 | guitare étouffée (très courte) | Distortion Guitar en quinte, notes coupées à 0,12 s |
| 12 | guitare en power chord (la quinte est dans le spectre) | Distortion Guitar, power chord, doublée gauche / droite |
| 4 | vide | (sert à couper une voie) |

## Contrôles

```sh
.venv\Scripts\python -m pytest              # tests : lecture, durée, hauteurs, bends, accords, ajouts de batterie
.venv\Scripts\python scripts\check_stems.py "Dr Mario.mod"   # chaque piste comparée au sample d'origine
```

`check_stems.py` rejoue chaque sample d'origine comme l'Amiga et le compare à son remplaçant : décalage de hauteur
(0 attendu ; il se trompe parfois sur les sons saturés) et calage dans le temps (0 ms attendu).

## Outils (tous gratuits)

| Outil | Rôle | Licence |
|---|---|---|
| [FluidSynth](https://www.fluidsynth.org/) 2.6.2 | joue le MIDI avec une SoundFont | LGPL |
| [GeneralUser GS](https://github.com/mrbumpy409/GeneralUser-GS) | SoundFont par défaut (≈ 30 Mo) | libre d'usage |
| [MuseScore General](https://musescore.org/) | autre SoundFont (≈ 40 Mo) | MIT |
| [OpenMPT](https://lib.openmpt.org/) (openmpt123) 0.8.10 | rendu de l'original | BSD |
| ffmpeg (paquet `imageio-ffmpeg`) | niveau sonore, MP3 | LGPL / GPL |
| [Pedalboard](https://github.com/spotify/pedalboard) | réverbération, compresseur, limiteur | GPL |
| mido, numpy, scipy, soundfile | MIDI, calcul, WAV | libres |

`tools\`, `.venv\` et `out\` ne sont pas dans git (lourds ou recréés).

## Limites et pistes

- Les SoundFonts General MIDI sont correctes, pas spectaculaires (surtout les guitares saturées). Pour un vrai saut
  de qualité, gratuit aussi : des **banques SFZ** (batteries multi-échantillonnées, guitares) avec
  [sfizz](https://sfz.tools/sfizz/), ou des **instruments VST3** gratuits (Surge XT, Vital…) et un simulateur d'ampli,
  que Pedalboard sait piloter.
- La détection des instruments est à faire (ou corriger) à l'oreille, sample par sample : c'est le cœur d'une future
  appli (écouter le sample, choisir un remplaçant dans une liste, réécouter).
- Formats gérés : `.mod` à 31 samples (M.K., FLT4, 6CHN, 8CHN…). Pas encore les `.xm`, `.s3m`, `.it`.
