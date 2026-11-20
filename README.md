# Remaster AMIGA Music

Un module Amiga (`.mod` ProTracker) rejoué avec des **instruments modernes**, puis mixé et enregistré en **MP3**.
Tout est gratuit et tourne sur le PC, sans rien installer dans Windows : les outils sont dans le dossier du projet.

Prototype en ligne de commande (17/11/2026), avant une éventuelle vraie appli PC.

Où en est le projet (20/11/2026) :
- **Toutes les musiques Amiga** d'archives de jeux (`in\lha\`) sont récupérées et rangées par jeu
  (`in\music\<Jeu>\`) : en .mod (d'origine ou converties avec libxmp) ou, pour les formats à lecteur intégré
  (TFMX, David Whittaker…), jouées par UADE. 631 originaux en MP3 dans `out\<Jeu>\`.
- **Remaster** (nouveaux instruments, MP3) : pour un .mod, et pour tout autre format (notes lues par UADE).
- **Tablatures** (guitares, basse) et **partition de batterie** : pour un .mod (*Dr Mario*).
- **Arrangement pour piano seul** (MP3 + partition) : pour n'importe quelle musique, avec une fiche automatique.
  Voir [Partitions et piano](#partitions-et-piano). Rien n'est validé à l'oreille par Claude : l'utilisateur écoute.
- **Instruments et effets VST3** (20/11/2026) : n'importe quel sample peut être joué par un VST (Surge XT, Dexed…),
  dont on **choisit le son à l'oreille** dans sa fenêtre pendant que les notes de la musique passent en boucle.
  Voir [VST : choisir le son à l'oreille](#vst--choisir-le-son-à-loreille).

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
5. **Rendu** (`remaster/render.py`) : chaque piste est jouée soit par un **instrument VST3** au son choisi à
   l'oreille (`remaster/vst.py`), soit par une **banque SFZ** (de vrais instruments
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

Les musiques sont rangées par jeu dans `in\music\<Jeu>\` (ex. `in\music\Dr Mario\Dr Mario.mod`) ; la fiche
d'instruments d'une musique est `songs\<musique>.json`. Les résultats aussi sont rangés par jeu :

- `out\<Jeu>\` : **toutes les musiques du jeu à plat**, en MP3 de l'original (`scripts\render_originals.py`) ;
- `out\<Jeu>\<musique>\` : un sous-dossier seulement pour une musique qu'on **retravaille** (remasters, piano,
  partitions, pistes séparées). Le chemin se déduit de celui de la musique (`remaster/paths.py`).

```sh
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python scripts\setup_tools.py        # FluidSynth, OpenMPT, SoundFonts, LilyPond, piano (≈ 430 Mo, une fois)
.venv\Scripts\python -m remaster "in\music\Dr Mario\Dr Mario.mod"
```

Dans `out\Dr Mario\` : `Dr Mario (original).mp3`, le module tel quel (rendu OpenMPT), pour comparer ; et dans
`out\Dr Mario\Dr Mario\`, le travail :

| Fichier | Contenu |
|---|---|
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
| `vsti` | un instrument VST3 : `{"plugin": "Surge XT", "state": "vst/Dr Mario/s05.bin", "bend_range": 2}` (fait par `python -m remaster.choisir`, voir [VST](#vst--choisir-le-son-à-loreille)) ; passe avant `sfz` et `program` |
| `sfz` | une banque SFZ : `{"bank": "black-and-green-guitars", "program": "Programs/07-black_twang.sfz", "cc": {}}` (banques connues : `remaster/library.py`) |
| `fx` | chaîne d'effets : `nam` (ampli), `cab` (baffle), `vst` (effet VST3, avec son état), et tout effet de Pedalboard (`PeakFilter`, `Compressor`, `Delay`…), avec `mix` facultatif (voir `remaster/fx.py`) |
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

## VST : choisir le son à l'oreille

Claude ne peut pas écouter : les sons réglés « à la main » sonnaient amateurs (retour du 17/11/2026). Avec un VST, on
part des presets faits par des gens qui écoutent, et c'est l'utilisateur qui choisit.

```sh
.venv\Scripts\python -m remaster.vst                                                  # les VST trouvés, essayés un par un
.venv\Scripts\python -m remaster.choisir "in\music\Dr Mario\Dr Mario.mod"             # les samples et ce qui les joue
.venv\Scripts\python -m remaster.choisir "in\music\Dr Mario\Dr Mario.mod" --sample 5  # liste des instruments, puis choix
.venv\Scripts\python -m remaster.choisir "in\music\Dr Mario\Dr Mario.mod" --sample 5 --vst "Surge XT" --debut 40
.venv\Scripts\python -m remaster.choisir "in\music\Dr Mario\Dr Mario.mod" --sample 5 --effet "DragonflyPlateReverb"
.venv\Scripts\python -m remaster "in\music\Dr Mario\Dr Mario.mod"                     # puis le remaster, avec le son choisi
```

- **Où sont les VST** (`remaster/vst.py`) : `tools\vst3\` (VST libres en zip, téléchargés par
  `scripts\setup_tools.py`), `tools\dragonfly\`, et `C:\Program Files\Common Files\VST3` (VST installés par leur
  installeur). Un VST se désigne par son nom de fichier sans « .vst3 ».
- **Catalogue** (`python -m remaster.vst`) : chaque VST est chargé **dans un processus à part** ; s'il fait planter
  le programme (c'est le cas de MT Power Drum Kit 2), seul ce processus tombe et le VST est marqué « inutilisable ».
  Résultat gardé dans `tools\vst3\catalogue.json`, refait pour un VST nouveau ou mis à jour (`--refaire` : tout).
- **Choisir** (`python -m remaster.choisir`) : la fenêtre du VST s'ouvre et **20 s de la musique passent en boucle**
  dans le VST, vers les haut-parleurs : seulement les notes de ce sample (toutes ses voies), avec ses hauteurs, ses
  bends et son volume. On change de preset, on l'entend aussitôt. On ferme la fenêtre quand ça plaît : l'**état du
  VST** (preset et réglages) est enregistré dans `songs\vst\<musique>\s05.bin` et la fiche reçoit la clé `vsti`.
  Relancer `choisir` sur le même sample repart du son déjà choisi. `--debut`, `--duree` : l'extrait ; `--volume` :
  volume d'écoute (0,5 ; le son est de toute façon écrêté à 0,9 pour les oreilles).
  `--effet NOM` : pareil pour un effet, ajouté à la fin de la chaîne `fx` du sample ; l'extrait est d'abord rendu
  avec l'instrument actuel.
- **Rendu** : la piste est jouée par le VST avec l'état enregistré. Le volume du module (CC 11, que beaucoup de
  synthés ignorent) devient la **vélocité** des notes (`"expression": "cc11"` pour le garder) ; les bends sont
  recalculés pour l'amplitude du synthé (`"bend_range"`, ±2 demi-tons par défaut : à mettre à 12 si on règle le
  synthé à ±12, sinon les glissandos larges sont écrêtés). Un autre preset choisi = la piste est refaite (l'état fait
  partie de la clé du cache) ; sans VST, les pistes déjà rendues restent bonnes.
- Certains VST ne chargent leur preset qu'au premier passage de son (Surge XT rendait du silence) : `vst.prepare`
  leur fait jouer un quart de seconde à vide avant le vrai rendu.

VST libres téléchargés par `scripts\setup_tools.py` (vérifiés le 20/11/2026 : chargés, une note jouée) :

| VST | Type | Pour quoi |
|---|---|---|
| [Surge XT](https://surge-synthesizer.github.io/) 1.3.4 (+ Surge XT Effects) | synthé hybride, ≈ 2 000 presets | leads, nappes, basses synthé, cloches, sons « Amiga » modernisés |
| [Dexed](https://asb2m10.github.io/dexed/) 1.1.0 | synthé FM façon DX7 | pianos électriques, cloches, basses FM, cuivres synthé |
| [JC303](https://github.com/midilab/jc303) 0.14.0 | basse acide façon TB-303 | basses techno / acid |
| [Firefly Synth 2](https://github.com/sjoerdvankreel/firefly-synth-2) 2.1.7 (+ FX) | synthé soustractif / FM | leads, nappes, effets |
| Dragonfly (Room, Hall, Plate, Early Reflections) | réverbérations | déjà utilisées au mixage |
| [sfizz](https://sfz.tools/sfizz/) 1.2.3 (`tools\sfizz\`, `sfizz_render.exe`) | lecteur SFZ complet | pas encore branché (voir ROADMAP) |

VST à installer soi-même (gratuits, souvent avec un compte ou un e-mail) : liste dans [docs/ROADMAP.md](docs/ROADMAP.md).
Après l'installation, `python -m remaster.vst` les essaie et les ajoute au catalogue.

## Récupérer la musique des archives de jeux (.lha)

Les archives de musiques de jeux Amiga (`in\lha\*.lha`, format « UnExoticA ») contiennent chacune les musiques
d'un jeu, avec un préfixe qui donne le format : `mod.` ProTracker, `med.` OctaMED, `p4x.` The Player 4, `sfx.`
SoundFX, `gmc.` Game Music Creator, `di.` Digital Illusions, `mdat.` TFMX, `dw.` David Whittaker, `rjp.` Richard
Joseph, `cust.` lecteur propre au jeu… (`smp.`, `smpl.` : les samples qui vont avec).

```sh
.venv\Scripts\python scripts\build_libxmp.py      # une fois : compile libxmp (il faut le gcc de MSYS2)
.venv\Scripts\python scripts\import_lha.py --essai   # ce qui serait fait
.venv\Scripts\python scripts\import_lha.py           # tout ranger dans in\music\<Jeu>\
```

Pour chaque jeu, `in\music\<Jeu>\` contient :
- **les musiques en .mod** (ce que lit le projet) : `<Jeu>.mod` s'il n'y en a qu'une, sinon `<Jeu> - <titre>.mod`
  (le nom sert aussi pour la fiche `songs\<nom>.json`, le MP3 `out\<Jeu>\<nom> (original).mp3` et le dossier de
  travail `out\<Jeu>\<nom>\`).
  Un fichier déjà en ProTracker ou en **Soundtracker 15 samples** est gardé tel quel ; un autre format est
  **converti** avec [libxmp](https://github.com/libxmp/libxmp) (`remaster/xmpconv.py`) ;
- **`originaux\`** : tous les fichiers de l'archive, tels quels, quel que soit le format ;
- et `in\music\INVENTAIRE.md` fait le point jeu par jeu.

La conversion (`remaster/xmpconv.py`) : libxmp lit le fichier (plus de 90 formats, dont beaucoup de modules
« compactés » des jeux), on relit ses motifs, samples et effets et on les réécrit en .mod. Les hauteurs suivent la
table de ProTracker (finetune compris) ; les motifs de longueur libre (OctaMED) sont coupés par 64 lignes ; le tempo
est **relevé en faisant jouer la musique par libxmp**, puis réécrit en commandes Fxx (OctaMED compte le tempo dans
une autre unité : sans ça, ses musiques duraient 2 à 7 fois trop longtemps). Contrôles : un .mod de *Dr Mario*
repasse à l'identique (notes, samples, durée) ; chaque conversion doit se jouer avec le lecteur du projet et durer
comme chez libxmp à 10 % près ; vérifié aussi avec OpenMPT sur des OctaMED et des SoundFX (même durée que
l'original, à 0,4 s près).

Bilan du 18/11/2026, 78 archives : **262 musiques en .mod dans 39 jeux** (175 d'origine, dont 23 Soundtracker ;
87 converties : OctaMED, The Player 4, SoundFX, Digital Illusions, Game Music Creator, Chiptracker, XM).
**161 fichiers à lecteur intégré** (TFMX, David Whittaker, Richard Joseph, `cust`…), gardés dans `originaux\` :
ils s'écoutent et se remasterisent avec UADE (section suivante). 1 fichier abîmé dans son archive (Rick Dangerous,
version alternative).

`in\lha\` et `in\music\` ne vont pas dans git (musiques sous droits, dépôt public) ; seul *Dr Mario* y est,
pour les tests.

## Les musiques à lecteur intégré (TFMX, David Whittaker…) : UADE

Beaucoup de musiques de jeux ne sont pas des partitions mais des programmes Amiga (TFMX de Chris Hülsbeck, David
Whittaker, Richard Joseph, lecteurs propres aux jeux…). **UADE** (logiciel libre) émule l'Amiga et fait tourner leur
vrai lecteur. Il est construit dans `tools\uade\` (il faut la partie POSIX de MSYS2 : `pacman -S gcc make pkgconf`) :

```sh
.venv\Scripts\python scripts\build_uade.py                     # une fois
.venv\Scripts\python scripts\render_originals.py              # l'original de toutes les musiques → MP3
.venv\Scripts\python -m remaster "in\music\Turrican 3\originaux\mdat.world_1" --sous-morceau 2
```

- **Écouter** (`scripts/render_originals.py`, qui fait aussi les .mod avec OpenMPT) : chaque sous-morceau devient
  `out\<Jeu>\<Jeu> - <titre> (n) (original).mp3`. Une autre version du même morceau (sous-dossier de l'archive :
  `Custom_Versions`…) porte son nom entre crochets : « Batman - cave [Custom Versions] ». Fin : quand le lecteur
  l'annonce ou après 5 s de silence. **Une musique qui boucle sans fin est jouée une fois** (de son début à la fin
  du premier tour de boucle), **ou deux fois si un tour fait moins de 2 minutes** (et tant pis si c'est encore
  court), avec un fondu de 4 s. La boucle est trouvée dans le journal de la puce son (`paula.find_loop`) : le plus
  petit décalage L et le premier instant A tels que chaque note (voie, sample, hauteur) revient L secondes plus tard
  jusqu'à la fin de l'enregistrement (20 min au plus, `--max`). Sans boucle ni fin en 20 min : les 5 premières
  minutes. **Les morceaux de moins de 15 s (jingles, bruitages) ne sont pas gardés** (`--min`, jugé sur le MP3).
  `--boucles` refait les MP3 UADE qui avaient été coupés à 5 min.
  18/11/2026 : **631 MP3 dans 78 dossiers de jeux** (237 .mod joués par OpenMPT, 394 morceaux joués par UADE) ;
  liste dans `in\music\ECOUTE.md`.
- **Remasteriser** (`remaster/paula.py`) : notre UADE est légèrement modifié (`scripts/build_uade.py`, `patch_uade`) :
  il écrit le **journal de la puce son Paula** (période, volume, adresse et longueur du sample de chaque voie ; le
  démarrage du DMA d'une voie = une note) et **copie chaque sample joué** depuis la mémoire Amiga. On en refait les
  ticks (20 ms) et les samples, sous la même forme qu'un .mod rejoué : la fiche d'instruments, le remaster, l'analyse
  des samples marchent tels quels. Vérifié sur *Dr Mario* joué par UADE : **4 386 notes, toutes au même instant et à
  la même hauteur** que notre lecteur ProTracker, et les 7 samples retrouvés à l'identique.
  Une fiche `songs\<Jeu> - <titre> (n).json` est créée au premier passage (un piano pour tout) : à compléter.
- **Piano** (MP3 + partition) : oui, une grille de lignes et de mesures est déduite des notes (`paula.on_grid`,
  voir [Partitions et piano](#partitions-et-piano)). **Tablatures et batterie** : pas encore pour ces musiques.

## Partitions et piano

La méthode complète, pour refaire la même chose avec un autre module : [docs/PARTITIONS.md](docs/PARTITIONS.md).

```sh
.venv\Scripts\python -m remaster.partitions "in\music\Dr Mario\Dr Mario.mod"   # tablatures + batterie (PDF), quelques secondes
.venv\Scripts\python -m remaster.piano "in\music\Dr Mario\Dr Mario.mod"        # piano : PDF + MP3 + MIDI, moins d'une minute
.venv\Scripts\python -m remaster.piano "in\music\Dr Mario\Dr Mario.mod" --sans-mp3
```

Les partitions partent des notes du remaster (et non du son) : on sait exactement ce que joue chaque voie, à la
double croche près. Une ligne de pattern = une double croche, 16 lignes = une mesure à 4/4 ; le tempo vient de la
vitesse du module (*Dr Mario* : ♩ = 150, 125 et 107). Chaque partie commence par une lettre encadrée avec le temps
dans le MP3 (A 0:00, B 0:06…), pour suivre en écoutant. Gravure : **LilyPond** (`remaster/lily.py`).

| Fichier (`out\Dr Mario\Dr Mario\partitions\`) | Contenu |
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
- **Piano pour n'importe quelle musique** (19/11/2026) : `python -m remaster.piano <fichier> [--sous-morceau N]`,
  ou une liste avec `scripts\piano_batch.py liste.txt` (lignes « fichier | n° »). Résultat dans
  `out\<Jeu>\<musique>\` : `(piano).mp3`, `.mid` et `partitions\… - Piano.pdf`.
  - Sans fiche, une **fiche automatique** est écrite (`remaster/roles.py`, à corriger à la main) : batterie (un
    ou deux sons fixes, ou un bruit à peu de hauteurs), basse (la ligne la plus grave), mélodie (le reste ; à chaque
    mesure, la voie la plus haute). Sans basse dans une mesure, la main gauche suit la note la plus grave qui sonne.
  - Musiques lues par UADE : une **grille** est déduite des notes (`paula.on_grid`) : l'écart le plus fréquent
    entre deux notes devient une croche (ou une double croche… pour rester sous ♩ = 220), calée sur les notes, et
    la barre de mesure sur les temps forts (notes longues et graves). La longueur est celle du MP3 d'origine ;
    quand la boucle y est jouée deux fois, la partition l'écrit une fois avec une **reprise** (levée à part).
  - Pas de vérification à l'oreille : la fiche automatique se trompe parfois (un lead saturé pris pour de la
    batterie…) ; on la corrige puis on relance.
  - Faits le 19/11/2026, à écouter : Strider (Custom Version 5 : fiche faite à la main ; Strider 1), Lotus 2
    bootup, Lotus title, Jim Power ingame_1 et ingame_3, Shadow of the Beast title_and_the_plains (2) et (4),
    Turrican 3 intro_and_title (1) et world_1 (1), Disposable Hero title, Great Giana Sisters ingame (1), Terry's
    Big Adventure, Batman chem (1), Skidz, Hybris title (le moins réussi : rythme irrégulier).

## Contrôles

```sh
.venv\Scripts\python -m pytest              # 66 tests, moins d'une minute (voir ci-dessous)
.venv\Scripts\python scripts\check_stems.py "in\music\Dr Mario\Dr Mario.mod"   # chaque piste comparée au sample d'origine
```

Les tests (`tests\`) couvrent : lecture des modules (ProTracker, Soundtracker 15 samples), durée et hauteurs,
bends, accords, ajouts de batterie, moteurs SFZ et amplis ; conversion libxmp (aller-retour exact sur *Dr Mario*) ;
import des archives (noms, versions alternatives, rangement par jeu) ; notes lues par UADE (identiques au lecteur
ProTracker sur *Dr Mario*), boucles (trouvées, notes au hasard tolérées, fausses boucles refusées), une ou deux
fois la boucle ; grille et premier temps ; tablatures (manche, durées, mesures complètes) ; piano (arrangement,
tierces, reprise, clavier) ; rôles des samples ; VST (recherche des plugins, catalogue qui écarte ceux qui
plantent, bends et volume envoyés au synthé, extrait en boucle, cache des pistes, rendu avec Surge XT et son état
rechargé). Ceux qui demandent UADE, libxmp, LilyPond ou Surge XT sont sautés s'ils manquent.

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
| [Pedalboard](https://github.com/spotify/pedalboard) | réverbération, compresseur, limiteur ; hôte des VST3 (fenêtre, rendu, écoute en direct) | GPL |
| [Surge XT](https://surge-synthesizer.github.io/), [Dexed](https://asb2m10.github.io/dexed/), [JC303](https://github.com/midilab/jc303), [Firefly Synth 2](https://github.com/sjoerdvankreel/firefly-synth-2) | instruments VST3 (`tools\vst3\`) | GPL-3.0 |
| [sfizz](https://sfz.tools/sfizz/) 1.2.3 | lecteur SFZ complet (`tools\sfizz\`) | BSD-2 |
| mido, numpy, scipy, soundfile | MIDI, calcul, WAV | libres |
| [7-Zip](https://www.7-zip.org/) (déjà installé sur le PC, ou dans `tools\7zip\`) | lecture des archives .lha | LGPL |
| [libxmp](https://github.com/libxmp/libxmp) 4.6.3 (compilée par `scripts\build_libxmp.py`) | lecture et conversion en .mod d'autres formats Amiga | MIT |
| [UADE](https://gitlab.com/uade-music-player/uade) 3.05 (modifié, compilé par `scripts\build_uade.py` avec le gcc POSIX de MSYS2) | joue les musiques Amiga à lecteur intégré ; journal de la puce son pour en tirer les notes | GPL-2.0 |
| [LilyPond](https://lilypond.org/) 2.24.4 | gravure des partitions et tablatures (PDF) | GPL-3.0 |
| [Salamander Grand Piano](https://freepats.zenvoid.org/Piano/acoustic-grand-piano.html) V3 (Alexander Holm, SF2 FreePats) | piano de l'arrangement (≈ 310 Mo) | CC-BY 3.0 |

`tools\`, `.venv\` et `out\` ne sont pas dans git (lourds ou recréés).

## Limites et pistes

Suite prévue (VST à installer, choix des sons à l'oreille) : [docs/ROADMAP.md](docs/ROADMAP.md).


- Le lecteur SFZ maison couvre ce qu'utilisent ces banques, pas toute la norme SFZ (pas de filtres, de LFO, ni de
  notes de relâchement). Les SoundFonts General MIDI restent pour les instruments sans banque SFZ (chœur).
- Les amplis NAM tournent en numpy, sans PyTorch : environ 1 min par piste de guitare de 6 min (les silences sont
  sautés).
- Certaines banques sont placées une octave au-dessus du son réel : *Black and Blue Basses* (mesuré : la touche 35
  sonne si 0). `remaster/library.py` (`KEY_OFFSET`) corrige ; `"key_offset"` dans `sfz` pour une autre banque.
- La détection des instruments est à faire (ou corriger) à l'oreille, sample par sample : c'est le cœur d'une future
  appli (écouter le sample, choisir un remplaçant dans une liste, réécouter).
- Formats : `.mod` à 31 samples (M.K., FLT4, 6CHN, 8CHN…) et Soundtracker à 15 samples lus directement ; OctaMED,
  The Player 4, SoundFX, Game Music Creator, XM… convertis en .mod par libxmp ; TFMX, David Whittaker, Richard
  Joseph, lecteurs maison… joués par UADE (notes lues dans le journal de la puce son). Non lu : Rick Dangerous.
