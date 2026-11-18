# Remaster AMIGA Music

Un module Amiga (`.mod` ProTracker) rejoué avec des **instruments modernes**, puis mixé et enregistré en **MP3**.
Tout est gratuit et tourne sur le PC, sans rien installer dans Windows : les outils sont dans le dossier du projet.

Prototype en ligne de commande (17/11/2026), avant une éventuelle vraie appli PC.
Depuis le 18/11/2026, il écrit aussi les **tablatures** (guitares, basse), la **partition de batterie** et un
**arrangement pour piano seul** (MP3 + partition) : voir [Partitions et piano](#partitions-et-piano).

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
5. **Rendu** (`remaster/render.py`) : chaque piste est jouée soit par une **banque SFZ** (de vrais instruments
   enregistrés note par note, plusieurs nuances et plusieurs prises par note) avec le lecteur maison
   `remaster/sfz.py`, soit par **FluidSynth** avec une **SoundFont** General MIDI (pour ce qui n'a pas encore de
   meilleure banque, comme le chœur). Les banques SFZ sont téléchargées **à la demande** (`remaster/library.py`) :
   seuls les échantillons réellement joués (quelques dizaines de Mo sur des banques de 1 Go).
6. **Chaîne d'effets par piste** (`remaster/fx.py`) : pour les guitares, une vraie guitare enregistrée sans effet (DI)
   passe dans un **ampli capturé par réseau de neurones** (Neural Amp Modeler, exécuté en numpy par
   `remaster/nam.py`) puis dans un **baffle** (réponse impulsionnelle), comme en studio ; égaliseurs, compresseurs,
   écho… Une partie peut être **doublée** (une guitare à gauche, une autre à droite, comme sur les disques de rock).
7. **Mixage** : panoramique, réverbération **Dragonfly Room** (VST3 open source, chargé par Pedalboard), compression,
   limiteur, niveau −14 LUFS, MP3 320 kbit/s CBR.
   Pour un son net : un nouveau coup de médiator **étouffe** les notes d'avant (`choke`), et les accords que le module
   doublait sur deux voies (pour faire plus fort) ne sont joués qu'une fois (`dedupe`) : la largeur vient de la double
   prise gauche / droite, avec deux guitares et deux amplis différents.
8. **Équilibrage sur l'original** (`remaster/reference.py`) : chaque nouvel instrument prend dans le mix la même place
   que son sample dans le module (sinon une guitare saturée écrase tout et la mélodie disparaît). `gain_db` dans la
   fiche ne sert plus qu'aux retouches.
9. **Version enrichie** (`remaster/extras.py`) : avec 4 voies, les musiciens gardaient souvent grosse caisse et caisse
   claire. On ajoute un **charleston** (toutes les 2 lignes, accentué sur les temps) et des **crashs** (début de chaque
   nouvelle partie, retour de la batterie après une pause), là où la batterie joue.

## Utilisation

Chaque module à traiter va dans son dossier `in\mod\<nom>\` (ex. `in\mod\Dr Mario\Dr Mario.mod`) ; les résultats sortent dans
`out\<nom>\` et la fiche d'instruments est `songs\<nom>.json`.

```sh
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python scripts\setup_tools.py        # FluidSynth, OpenMPT, SoundFonts, LilyPond, piano (≈ 430 Mo, une fois)
.venv\Scripts\python -m remaster "in\mod\Dr Mario\Dr Mario.mod"
```

Dans `out\Dr Mario\` :

| Fichier | Contenu |
|---|---|
| `Dr Mario (original).mp3` | le module tel quel (rendu OpenMPT), pour comparer |
| `Dr Mario (remaster fidèle).mp3` | mêmes notes, nouveaux instruments |
| `Dr Mario (remaster enrichi).mp3` | pareil + charleston et crashs ajoutés |
| `Dr Mario (remaster).mid` | la partition en MIDI, pour la reprendre dans un logiciel de musique |
| `samples\` | les samples d'origine en WAV, pour les écouter |
| `stems\` | chaque piste séparée (FLAC), avant les derniers réglages d'égaliseur ; sert aussi de **cache** |
| `Dr Mario (piano).mp3`, `.mid` | l'arrangement pour piano seul (`python -m remaster.piano`) |
| `partitions\` | tablatures, batterie et piano en PDF, avec leur source LilyPond (`.ly`) |

Le premier rendu prend une dizaine de minutes (les amplis NAM). Ensuite, seules les pistes dont les notes,
l'instrument ou l'ampli changent sont refaites : changer un volume, un panoramique, une réverbération ou un égaliseur
placé après l'ampli ne prend qu'une minute et demie.

Pour un autre module, la première fois, une **fiche d'instruments** `songs\<nom>.json` est créée (un piano pour
tout) : à compléter, puis relancer.

### La fiche d'instruments (`songs\Dr Mario.json`)

Pour chaque sample (`"1"` à `"31"`) :

| Clé | Rôle |
|---|---|
| `sfz` | une banque SFZ : `{"bank": "black-and-green-guitars", "program": "Programs/07-black_twang.sfz", "cc": {}}` (banques connues : `remaster/library.py`) |
| `fx` | chaîne d'effets : `nam` (ampli), `cab` (baffle), et tout effet de Pedalboard (`PeakFilter`, `Compressor`, `Delay`…), avec `mix` facultatif (voir `remaster/fx.py`) |
| `double` | double prise gauche / droite : `{"sfz": autre banque, "width": 0.85, "delay_ms": 11}` |
| `by_channel` | réglages propres à une voie du module : `{"2": {...}}` |
| `choke` | un nouveau coup coupe le précédent (guitares, basse) |
| `dedupe` | `false` pour garder les notes que le module double sur plusieurs voies (par défaut : jouées une fois) |
| `program` | sinon, instrument General MIDI joué par FluidSynth (0 piano, 30 guitare saturée, 33/34 basse, 52 chœur…) |
| `drum` | ou bien un son de batterie (note GM : 36 grosse caisse, 38 caisse claire, 42 charleston, 49 crash) |
| `drum_kit` | kit de batterie (0 Standard, 16 Power, 25 TR-808…) |
| `chord` | notes ajoutées (demi-tons) : `[0, 7, 12]` power chord |
| `transpose` | décalage en demi-tons (−12 : une octave plus bas) |
| `root` | note MIDI du sample au C-2, si la détection automatique se trompe |
| `max_length` | coupe les notes (secondes) : utile pour un son étouffé |
| `velocity`, `gain_db`, `pan`, `reverb` | force de frappe, volume, panoramique (−1 à 1, ou par voie), réverbération |
| `soundfont` | une autre SoundFont pour cet instrument |
| `mute` | ne pas jouer ce sample |

`master` : `loudness`, `fx` (égaliseur du mix), `reverb` (VST3 Dragonfly et ses réglages), `balance`.
Attention : l'équilibrage sur l'original (`"balance": "original"`) compense le volume des égaliseurs ; pour rendre
un instrument plus présent, utiliser `gain_db`.

`extras` règle les ajouts de la version enrichie (`gain_db` : tant de dB sous un coup de la batterie d'origine).

### Instruments retenus pour *Dr Mario*

Les noms des samples sont des messages (« composed by betrayer », « greets to tokyo kid »…) : les instruments ont
été reconnus à l'analyse du son et de leur rôle dans les patterns.

| Sample | Ce que c'est | Remplacé par |
|---|---|---|
| 1, 2 | grosse caisse, caisse claire | *Big Rusty Drums* (kick court avec l'attaque de la batte, renforcé vers 5 kHz) |
| 3 | basse (accordée en sol#) | *Black and Blue Basses* (basse « darkblack » aux doigts), compresseur, un peu de saturation |
| 5 | lead avec bends | guitare *green* (son tenu) → ampli 5152 Lead + TS9 (NAM) → baffle Greenback → écho léger |
| 10 | chœur | Choir Aahs (GeneralUser GS, FluidSynth) |
| 11 | guitare étouffée (très courte) | staccato coupé à 0,12 s, en quinte ; mêmes guitares et amplis que la rythmique |
| 12 | guitare en power chord (la quinte est dans le spectre) | power chords (3 cordes) : à gauche guitare *black* → Engl Savage, à droite guitare *green* → 6505+ MXR ; baffle 4×12 Greenback |
| 4 | vide | (sert à couper une voie) |
| ajouts | charleston, crashs (version enrichie) | *Big Rusty Drums* |

## Récupérer les modules des archives de jeux (.lha)

Les archives de musiques de jeux Amiga (`in\lha\*.lha`, format « UnExoticA ») contiennent chacune les musiques
d'un jeu, avec un préfixe qui donne le format : `mod.` = ProTracker ou Soundtracker (ce que lit le projet),
`med.` OctaMED, `mdat.` TFMX, `dw.` David Whittaker, `rjp.` Richard Joseph, `cust.` lecteur propre au jeu…

```sh
.venv\Scripts\python scripts\import_lha.py --essai   # ce qui serait fait
.venv\Scripts\python scripts\import_lha.py           # range les modules dans in\mod\<Jeu>\
```

- Un module seul : `in\mod\<Jeu>\<Jeu>.mod` ; plusieurs : `<Jeu> - <titre>.mod`. Le nom sert aussi pour la fiche
  `songs\<nom>.json` et le dossier de sortie `out\<nom>\` (un dossier par musique).
- Chaque fichier est lu directement dans l'archive (7-Zip, sans extraction sur le disque), puis gardé seulement s'il
  se lit **et se joue** avec le lecteur du projet. Un module déjà présent (mêmes octets) n'est pas recopié.
- Les modules **Soundtracker à 15 samples** (l'ancêtre de ProTracker, sans signature « M.K. ») sont lus aussi
  (`modfile.is_soundtracker`) : 23 des modules importés sont dans ce format.
- 18/11/2026, 78 archives : **175 modules** dans 26 jeux ; 8 fichiers `mod.` refusés (Warzone, Wolfchild : un autre
  format malgré le nom) ; 50 jeux n'ont que d'autres formats (voir [ROADMAP](docs/ROADMAP.md)).
- `in\lha\` et les modules importés ne vont pas dans git (musiques sous droits) ; seul *Dr Mario* y est, pour les tests.

## Partitions et piano

La méthode complète, pour refaire la même chose avec un autre module : [docs/PARTITIONS.md](docs/PARTITIONS.md).

```sh
.venv\Scripts\python -m remaster.partitions "in\mod\Dr Mario\Dr Mario.mod"   # tablatures + batterie (PDF), quelques secondes
.venv\Scripts\python -m remaster.piano "in\mod\Dr Mario\Dr Mario.mod"        # piano : PDF + MP3 + MIDI, moins d'une minute
.venv\Scripts\python -m remaster.piano "in\mod\Dr Mario\Dr Mario.mod" --sans-mp3
```

Les partitions partent des notes du remaster (et non du son) : on sait exactement ce que joue chaque voie, à la
double croche près. Une ligne de pattern = une double croche, 16 lignes = une mesure à 4/4 ; le tempo vient de la
vitesse du module (*Dr Mario* : ♩ = 150, 125 et 107). Chaque partie commence par une lettre encadrée avec le temps
dans le MP3 (A 0:00, B 0:06…), pour suivre en écoutant. Gravure : **LilyPond** (`remaster/lily.py`).

| Fichier (`out\Dr Mario\partitions\`) | Contenu |
|---|---|
| `Guitare 1 (lead).pdf` | portée + tablature : la ligne de lead la plus haute à chaque mesure, bends (b. ½, b. 1, lâcher), glissandos, vibrato |
| `Guitare 2 (rythmique).pdf` | power chords et quintes étouffées (P.M. - - -, accords ouverts accentués), plus les autres lignes de lead |
| `Basse.pdf` | portée + tablature 4 cordes |
| `Batterie (version enrichie).pdf` | grosse caisse, caisse claire, plus le charleston et les crashs ajoutés |
| `Piano.pdf` | l'arrangement pour piano (deux portées) |

- **Tablatures** (`remaster/partitions.py`, `remaster/fretboard.py`) : accordage standard (guitare mi-la-ré-sol-si-mi,
  basse mi-la-ré-sol). Pour chaque note ou accord, toutes les positions jouables sont essayées (une note par corde,
  4 cases d'écart au plus, cordes voisines) ; la suite retenue bouge le moins la main et reste basse sur le manche.
  Une note trop grave pour l'instrument monte d'une octave (40 pour la guitare rythmique : le module descend au do
  grave) ; un accord injouable (deux voies du module qui jouent des accords différents) perd des notes (24 sur 1 599).
- **Qui joue quoi** : section `partitions` de la fiche (`songs/Dr Mario.json`) : samples de chaque musicien ; une
  partie `"lead": true` prend, à chaque mesure, la voie du module qui joue le plus haut.
- **Piano** (`remaster/piano.py`, section `piano` de la fiche) : main droite = mélodie du lead (hampes en haut) et
  accords de trois sons dessous ; les guitares jouant des quintes sans tierce, la tierce vient de la tonalité du
  passage (profils de Krumhansl) et des notes de la mélodie. Main gauche = le riff étouffé une octave plus bas, piqué,
  ou la basse en octaves. Pédale changée à chaque accord, sauf dans les riffs. Son : **Salamander Grand Piano V3**
  (Yamaha C5, 16 nuances, SoundFont jouée par FluidSynth) dans la réverbération **Dragonfly Hall**, −16 LUFS.
  Le MP3 garde le tempo du module : il se cale sur l'original et les remasters.

## Contrôles

```sh
.venv\Scripts\python -m pytest              # tests : lecture, durée, hauteurs, bends, accords, ajouts de batterie
.venv\Scripts\python scripts\check_stems.py "in\mod\Dr Mario\Dr Mario.mod"   # chaque piste comparée au sample d'origine
```

`check_stems.py` rejoue chaque sample d'origine comme l'Amiga et le compare à son remplaçant : décalage de hauteur
(0 attendu ; il se trompe parfois sur les sons saturés) et calage dans le temps (0 ms attendu).

## Outils (tous gratuits)

| Outil | Rôle | Licence |
|---|---|---|
| [Black and Green Guitars](https://github.com/sfzinstruments/karoryfer.black-and-green-guitars) (Karoryfer) | deux guitares électriques DI | CC0 |
| [Black and Blue Basses](https://github.com/sfzinstruments/karoryfer.black-and-blue-basses) (Karoryfer) | basses électriques | CC0 |
| [Virtuosity Drums](https://github.com/sfzinstruments/virtuosity_drums) (Versilian, Karoryfer) | batterie multi-micros | CC0 |
| [NAM_models](https://github.com/pelennor2170/NAM_models) | captures d'amplis (5150, 6505+, JCM2000…) pour Neural Amp Modeler | GPL-3.0 |
| Jesters Brutal / Emerald Pack, via [OrbitCab](https://github.com/darwinscat/orbitcab) | réponses impulsionnelles de baffles 4×12 | CC0 |
| [FluidSynth](https://www.fluidsynth.org/) 2.6.2 | joue le MIDI avec une SoundFont | LGPL |
| [GeneralUser GS](https://github.com/mrbumpy409/GeneralUser-GS) | SoundFont par défaut (≈ 30 Mo) | libre d'usage |
| [MuseScore General](https://musescore.org/) | autre SoundFont (≈ 40 Mo) | MIT |
| [OpenMPT](https://lib.openmpt.org/) (openmpt123) 0.8.10 | rendu de l'original | BSD |
| ffmpeg (paquet `imageio-ffmpeg`) | niveau sonore, MP3 | LGPL / GPL |
| [Dragonfly Reverb](https://github.com/michaelwillis/dragonfly-reverb) 3.2.10 | réverbération (VST3) | GPL-3.0 |
| [Big Rusty Drums](https://github.com/sfzinstruments/karoryfer.big-rusty-drums) (Karoryfer) | batterie | CC0 |
| [Pedalboard](https://github.com/spotify/pedalboard) | réverbération, compresseur, limiteur | GPL |
| mido, numpy, scipy, soundfile | MIDI, calcul, WAV | libres |
| [7-Zip](https://www.7-zip.org/) (déjà installé sur le PC, ou dans `tools\7zip\`) | lecture des archives .lha | LGPL |
| [LilyPond](https://lilypond.org/) 2.24.4 | gravure des partitions et tablatures (PDF) | GPL-3.0 |
| [Salamander Grand Piano](https://freepats.zenvoid.org/Piano/acoustic-grand-piano.html) V3 (Alexander Holm, SF2 FreePats) | piano de l'arrangement (≈ 310 Mo) | CC-BY 3.0 |

`tools\`, `.venv\` et `out\` ne sont pas dans git (lourds ou recréés).

## Limites et pistes

Suite prévue (dont le passage à de vrais VST choisis à l'oreille) : [docs/ROADMAP.md](docs/ROADMAP.md).


- Le lecteur SFZ maison couvre ce qu'utilisent ces banques, pas toute la norme SFZ (pas de filtres, de LFO, ni de
  notes de relâchement). Les SoundFonts General MIDI restent pour les instruments sans banque SFZ (chœur).
- Les amplis NAM tournent en numpy, sans PyTorch : environ 1 min par piste de guitare de 6 min (les silences sont
  sautés).
- Certaines banques sont placées une octave au-dessus du son réel : *Black and Blue Basses* (mesuré : la touche 35
  sonne si 0). `remaster/library.py` (`KEY_OFFSET`) corrige ; `"key_offset"` dans `sfz` pour une autre banque.
- La détection des instruments est à faire (ou corriger) à l'oreille, sample par sample : c'est le cœur d'une future
  appli (écouter le sample, choisir un remplaçant dans une liste, réécouter).
- Formats gérés : `.mod` à 31 samples (M.K., FLT4, 6CHN, 8CHN…) et Soundtracker à 15 samples. Pas encore les `.xm`,
  `.s3m`, `.it`, ni les formats à lecteur intégré (TFMX, OctaMED…) : voir la ROADMAP.
