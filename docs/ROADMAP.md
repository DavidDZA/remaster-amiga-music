# Roadmap

## En cours (21/11/2026) : remaster « fidèle à l'esprit des instruments » des 10 musiques électro

Les remasters électro (`scripts\style_electro.py`) étaient un **malentendu** : l'utilisateur voulait que ces
musiques, déjà plutôt électro, soient remasterisées **en restant fidèles à l'esprit de chaque instrument** (un
piano reste un piano, une basse synthé reste une basse synthé, une batterie garde son genre), pas un style électro
plaqué. **Ne pas toucher** aux versions électro ni aux anciennes versions.

Liste : Hybris title, Terrys Big Adventure, Lotus 2 bootup, Great Giana Sisters ingame (1), Jim Power ingame_1 et
ingame_3, Shadow of the Beast title_and_the_plains (4), Strider (1), Turrican 3 world_1 (1), Batman chem (1).

Méthode prévue (sans oreilles) : pour chaque sample, le son moderne **le plus proche du sample d'origine**, comparé
note pour note (spectre et enveloppe : attaque, déclin, tenue) parmi les 128 instruments General MIDI de
GeneralUser GS (rendus sur la même note) ; pour la batterie, la pièce la plus proche dans les kits GM (un kit par
musique). Résultat prévu : `<musique> (remaster fidèle).mp3` dans le dossier de la musique, fiche à part
`songs\<musique> (fidèle).json` (la fiche électro reste).

## Fait le 20/11/2026 : les VST, choisis à l'oreille (« option 1 »)

Décidé le 17/11/2026 (le rendu fait sans oreilles sonnait amateur : guitares nasillardes, kick inaudible, écho, flou).
L'utilisateur veut **le plus de VST possible**, pas seulement batterie, basse et guitare : d'autres musiques suivront
(synthés à la Hülsbeck, orchestre, orgue…).

Fait : `remaster/vst.py` (recherche dans `tools\vst3\`, `tools\dragonfly\` et `C:\Program Files\Common Files\VST3`,
catalogue qui essaie chaque VST dans un processus à part, rendu d'une piste, écoute en direct), clé `vsti` de la fiche,
effets `vst` avec leur état, et `python -m remaster.choisir` : la fenêtre du VST s'ouvre, l'extrait de la musique passe
en boucle dans le VST, on ferme quand le son plaît, l'état est enregistré (`songs\vst\<musique>\`). Mode d'emploi :
README, section « VST ». Vérifié : chargement, rendu, état rechargé (Surge XT ne chargeait son preset qu'au premier
passage de son : corrigé), écoute en boucle en temps réel fenêtre ouverte.

**Premier essai** (20/11/2026, l'utilisateur n'avait pas le temps : presets choisis par Claude, sans écoute) :
Dr Mario, lead → Surge XT « Synth Guitar », chœur → « Retrochoir » (`scripts\essai_vst.py`, fiche
`songs\Dr Mario - essai VST 1.json`, MP3 dans `out\Retravaillées\Dr Mario\`). Verdict : **« encore pire »**.

Ensuite : **liste d'extraits** (`scripts\extraits.py`) : 9 sons pour le lead et 9 pour le chœur, le même passage
de 20 s dans le mix, au même niveau. Verdict : « bof, rien ne semble réaliste. Peut-être on est à la limite du VST
libre ». Demande : plus de choix, des **voix plus naturelles** pour le chœur, un **lead heavy métal percutant et
sec**, l'**autre guitare** aussi (néo-métal bien lourde, mais qui ne bave pas), une **batterie rock ou métal**.

**Série 2** (20/11/2026) : 9 batteries (4 vraies batteries libres multi-micros, le lecteur SFZ les lit maintenant),
10 guitares rythmiques, 10 leads, 4 chœurs (détail dans le README). **À écouter** ; l'utilisateur donne un numéro par
partie.

**Choix de l'utilisateur** (série 2) : batterie 7 (Naked Drums, son rock compressé), guitare rythmique 7 (6505+
canal rouge + MXR, moins de gain, serré), lead 7 (guitare black, Engl E530 + DS-1, sec), chœur 1 (MuseScore). Mis
dans la fiche (`scripts\appliquer_choix.py`). Son avis sur le résultat d'ensemble : « toujours pas fou, ça ne
ressemble pas du tout à des vrais sons de studio ; essaie de faire sonner ça métal comme tu peux ». D'où la
**production métal** (`scripts\production_metal.py` : jeu humanisé, deux vraies prises de guitare, basse en
parallèle, compression parallèle de la batterie, mix plus dense) : **à écouter**.

Verdict sur Dr Mario métal (21/11/2026) : **« une catastrophe le son »**. L'utilisateur passe à des musiques plus
électro (`scripts\style_electro.py`, 10 musiques, instruments choisis par Claude) : **à écouter**. Lotus title :
partitions et version métal faites (même recette que Dr Mario), à écouter et relire.

Limites, à dire franchement :
- **Chœur naturel** : rien de libre et téléchargeable sans compte ni e-mail (les banques SFZ libres n'ont que des
  chœurs General MIDI ; celui de « Discord SFZ GM » est une sinusoïde). Les meilleures pistes gratuites demandent une action de l'utilisateur : **Spitfire LABS
  Choir** (compte Spitfire, VST3) ou **Dave Choir** (Decent Samples, SFZ, adresse e-mail ; une voix d'homme
  enregistrée 16 fois, baryton, « ah » et « oh »). Une fois téléchargés, on les met dans la série suivante.
- **Guitare métal** : pas de banque de guitare métal libre ; la voie réaliste reste une guitare enregistrée sans
  effet (Black and Green) dans une capture d'ampli NAM. Les captures du dépôt NAM_models n'ont pas de Mesa
  Rectifier (le son néo-métal type) ; le site ToneHunt / TONE3000 en a des milliers, souvent avec un compte.
- **Jeu mécanique** : les notes viennent d'un module de 4 voies, vélocités fixes et rythme exact. Humanisation
  faite le 20/11/2026 (`midi.humanize`) ; restent : de vrais étouffements (palm mute) de la guitare rythmique (la
  banque Black and Green n'en a pas : staccato coupé), ghost notes et roulements de caisse claire, toms, ride,
  doubles pédales — une batterie écrite pour du métal, pas seulement grosse caisse / caisse claire du module.
- `sfizz_render.exe` (lecteur SFZ complet) n'a pas pu être lancé : refusé par le contrôle de sécurité de Claude Code
  (programme téléchargé). Le lecteur maison a été complété à la place.

VST libres déjà là (zip, `scripts\setup_tools.py`) : Surge XT (+ Effects), Dexed, JC303, Firefly Synth 2 (+ FX),
Dragonfly ; sfizz (lecteur SFZ) en ligne de commande. Surge XT en version **portable** : sans elle, aucun preset
(seulement le son vide).

### VST à installer par l'utilisateur (gratuits)

Après chaque installation : `python -m remaster.vst` (essai et ajout au catalogue). Ceux marqués « compte » demandent
une inscription gratuite. Rien de tout ça n'est encore essayé dans l'outil.

| Famille | VST | Remarque |
|---|---|---|
| Orchestre, pianos, chœurs, guitares… | **Spitfire LABS** | des dizaines d'instruments enregistrés ; appli Spitfire, compte |
| Orchestre | **BBC Symphony Orchestra Discover** (Spitfire) | cordes, bois, cuivres, percussions ; compte |
| Tout instrument échantillonné | **Decent Sampler** + bibliothèques gratuites (Pianobook, Decent Samples) | des centaines d'instruments |
| Banques SFZ | **sfizz** (VST3, installeur sfizz-ui) | choisir une banque SFZ dans une fenêtre ; ouvre VCSL, Virtual Playing Orchestra… |
| Synthés | **Vital** (compte), **OB-Xd 2**, **Odin 2**, **Vaporizer2**, **TAL-NoiseMaker**, **u-he Zebralette 3**, **Tyrell N6** | leads, nappes, basses ; OB-Xd, Odin 2, Vaporizer2 : open source |
| Batterie | **Steven Slate Drums 5.5 Free** (compte), **Sitala** | MT Power Drum Kit 2 est installé mais **plante** dans Pedalboard (voir plus bas) |
| Basse | **Ample Bass P Lite II** | basse électrique |
| Guitare acoustique | **Ample Guitar M Lite II** | |
| Amplis guitare | **Neural Amp Modeler** (open source), **Ignite Emissary + NadIR**, **ML Sound Lab Amped Roots Free** | |
| Effets | **Valhalla Supermassive** (réverb, écho), **TDR Nova** (égaliseur), **TDR Kotelnikov** (compresseur), **Airwindows Consolidated** (open source, des centaines d'effets), **Chow Tape Model** | |

Installer en VST3 dans le dossier proposé (`C:\Program Files\Common Files\VST3`) ; un installeur qui laisse choisir
le dossier peut aussi viser `tools\vst3\` du projet.

### Reste à faire côté VST

- **Choisir les sons à l'oreille** sur une première musique (Dr Mario, ou une musique de synthé), puis comparer au
  remaster actuel.
- **MT Power Drum Kit 2** plante au chargement (accès mémoire interdit dans le VST, même avec Pedalboard 0.8.9, 0.9.6,
  0.9.26 ; d'autres hôtes le signalent aussi en VST3). Pistes : un autre hôte (DawDreamer, Carla), ou une autre batterie.
- **Amplitude du pitch bend** : 2 demi-tons par défaut ; la mesurer en jouant une note bendée et en lisant la hauteur,
  au lieu de la demander.
- **Nom du preset** dans la fiche (Pedalboard ne le donne pas : à lire dans l'état quand le VST l'y écrit ; fait
  pour Surge XT dans `scripts\essai_vst.py`, à mettre dans `choisir`).
- **Le contrôle de hauteur** (`check_stems.py`) se trompe d'octave sur les chœurs (formants) : la hauteur d'une note
  jouée seule (autocorrélation) est plus sûre.
- **sfizz** : remplacer le lecteur SFZ maison (`remaster/sfz.py`, sans filtres ni LFO ni relâchement) par
  `sfizz_render.exe`, ou par le VST sfizz une fois installé.
- **Choisir pour une partie doublée** (`double`, prise de droite) et **par voie** (`by_channel`) : `choisir` règle le
  sample entier, prise de gauche.
- Plus de VST libres en zip à ajouter à `scripts\setup_tools.py` au fil des trouvailles.

## Fait le 18/11/2026 : partitions et piano

Tablatures (2 guitares, basse), batterie de la version enrichie, arrangement pour piano seul (MP3 + PDF). À écouter
et relire par l'utilisateur : doigtés, choix des tierces au piano, son du piano (rien n'a été validé à l'oreille).

Pistes : exporter aussi en **Guitar Pro** / **MusicXML** (pour TuxGuitar, MuseScore, Songsterr) ; noms d'accords
(E5, D5…) au-dessus de la guitare rythmique ; une partition piano simplifiée (niveau débutant) ; batterie fidèle
(sans les ajouts) sur demande.

## Musiques à lecteur intégré (TFMX, David Whittaker…)

Fait le 18/11/2026 : UADE construit dans tools\uade (modifié pour écrire le journal de la puce son et copier les
samples), les originaux enregistrés en MP3 (une fois la boucle, deux si elle fait moins de 2 min), et remaster
possible (`python -m remaster <fichier> --sous-morceau N`), vérifié note pour note sur Dr Mario.

## Fait le 19/11/2026 : piano pour n'importe quelle musique

Fiche automatique (`remaster/roles.py`), grille déduite des notes (`paula.on_grid`), reprise quand la boucle est
jouée deux fois, harmonie par demi-mesure. 16 arrangements faits (liste dans le README), **à écouter par
l'utilisateur** : son retour dira ce qu'il faut corriger (rôles mal devinés, grille, accords, main gauche).

## À faire

- **Piano : accord général** (`tuning_cents`) à mesurer et mettre dans toutes les fiches : l'utilisateur signale
  « énormément de problèmes sur les partitions piano » ; Giana en était un (mélodie un demi-ton au-dessus de la
  basse). Mesurer chaque piano avec `scripts\compare_chroma.py` (avec l'accord de l'original) pour trouver les
  passages faux, puis corriger rôle par rôle (mélodie préférée, `"prefer"`).
- **Retour d'écoute** sur les 16 pianos ; corriger les fiches (`songs\*.json`) et les règles de `roles.py` en
  conséquence.
- **Hybris** (lecteur de synthé) : grille irrégulière, partition peu lisible ; chercher un pas qui varie, ou des
  triolets.
- **Tablatures et batterie pour les musiques UADE** : brancher `remaster.partitions` sur `paula.load_grid` comme
  le piano (la grille et la fiche existent déjà) ; ajouter dans la fiche automatique les parties guitare / basse.
- **Rick Dangerous** (`cust.`) : UADE ne le reconnaît pas ; la version alternative est abîmée dans l'archive.
- **23 morceaux sans boucle trouvée**, encore coupés à 5 min (Batman « music », Bone Cruncher, Hybris, Pang, RoboCop,
  Strider, Double Dragon 2…) : leurs notes ne se répètent pas à 99 % sur 20 min. Pistes : voies qui bouclent
  chacune à leur rythme (chercher une boucle par voie), beaucoup de notes tirées au sort (seuil plus large),
  ou comparer le son plutôt que les notes.
- Piano : les 8 mesures muettes du début de Lotus 2 bootup (batterie seule) ; une option pour commencer à la
  première note.

## Ensuite

- **Écoute rapide** : un extrait de 20 s rendu en quelques secondes, pour comparer deux réglages.
- **Appli PC** (voir `IDEES-APPLIS.md`, idée 3) : liste des samples, « Écouter l'original », choix de l'instrument
  (liste déroulante), « Écouter le remplaçant », puis « Créer le MP3 ».
- **Batterie enrichie plus variée** : ride, toms de transition, ouverture du charleston.
- **Lecteur SFZ** : filtres, LFO, notes de relâchement ; banques qui ne passent pas encore (DRSKit de DrumGizmo :
  variables `$v61h` non résolues).
