# Partitions, tablatures et piano : la méthode

Comment on a fait, le 18/11/2026, les tablatures (2 guitares + basse), la partition de batterie et l'arrangement
pour piano seul de *Dr Mario*. Ce guide sert à refaire la même chose pour un autre module.

## En bref

```sh
.venv\Scripts\python scripts\setup_tools.py                       # une fois : LilyPond et le piano dans tools\
.venv\Scripts\python scripts\dump_patterns.py "in\music\morceau\morceau.mod"        # 1. comprendre le module
#                                                                    2. compléter songs\morceau.json
.venv\Scripts\python -m remaster "in\music\morceau\morceau.mod"                     # 3. le remaster (les partitions en suivent les notes)
.venv\Scripts\python -m remaster.partitions "in\music\morceau\morceau.mod"          # 4. tablatures + batterie (PDF)
.venv\Scripts\python -m remaster.piano "in\music\morceau\morceau.mod"               # 5. piano : PDF + MP3 + MIDI
.venv\Scripts\python scripts\preview_pages.py "out\Jeu\morceau\partitions"   # 6. relire les pages en images
.venv\Scripts\python -m pytest                                     # 7. tests
```

Puis l'utilisateur écoute le MP3 du piano et lit les partitions : **rien n'est validé à l'oreille** par Claude.

## Le principe

Un `.mod` est déjà une partition : on ne transcrit pas un son, on relit les notes. Le lecteur (`remaster/player.py`)
rejoue le module tick par tick comme ProTracker ; `remaster/score.py` place chaque attaque sur la grille des lignes.

- **1 ligne de pattern = 1 double croche**, **16 lignes = 1 mesure à 4/4**, 1 pattern de 64 lignes = 4 mesures.
  Vérifié sur *Dr Mario* : caisse claire aux lignes 4 et 12 de chaque groupe de 16 (temps 2 et 4).
  Un autre module peut être écrit autrement (une ligne = une croche, mesures de 12 lignes en 3/4…) : regarder où
  tombe la caisse claire avec `dump_patterns.py` avant de croire la grille. Les patterns coupés (Dxx) donnent des
  mesures plus courtes : `score.bars()` les gère (mesure de moins de 16 lignes).
- **Tempo** : noire = 60 / (4 × durée d'une ligne). Vitesse 6 à 125 BPM → ♩ = 125 ; vitesse 5 → 150 ; 7 → 107.
  Le tempo écrit est celui de la majorité des lignes de la mesure (un F06 sur la dernière ligne seulement, petit
  ralenti du module, n'est pas noté).
- **Hauteur** : celle du remaster (racine du sample + transposition + accord de la fiche). Les partitions suivent
  donc le MP3 remasterisé, power chords compris.
- **Repères** : une lettre encadrée à chaque nouvelle partie (le pattern change) avec le temps dans le MP3
  (A 0:00, B 0:06…). Le piano garde le tempo du module, donc les mêmes temps valent pour tous les MP3.

## Étape 1 : comprendre le module

Les partitions demandent un module à lignes et mesures (ProTracker, Soundtracker, ou converti en .mod). Les musiques
à lecteur intégré lues par UADE n'en ont pas encore (voir la ROADMAP).

Le module vient souvent d'une archive de jeu : `scripts\import_lha.py` range dans `in\music\<Jeu>\` toutes les
musiques des archives de `in\lha\` (converties en .mod si besoin) (voir le README). Les résultats d'une musique qu'on retravaille vont dans `out\<Jeu>\<nom>\`.

`scripts/dump_patterns.py "in\music\morceau\morceau.mod"` affiche les samples (durée, note au C-2) et, pour chaque pattern, quels
samples jouent sur quelles voies et quels effets. Avec des numéros de patterns, il affiche le détail comme un tracker.

Ce qu'on a appris sur *Dr Mario* (à chercher de la même façon ailleurs) :

| Sample | Rôle | Indice |
|---|---|---|
| 1, 2 | grosse caisse, caisse claire | 1 sur les temps 1 et 3, 2 sur 2 et 4 |
| 3 | basse | toujours la voie 4, croches répétées |
| 5 | lead | notes aiguës, effets 1xx/2xx sur des notes tenues = bends |
| 10 | chœur | notes longues, en nappes, doublé sur deux voies |
| 11 | guitare étouffée | sample de 0,19 s, galops de doubles croches |
| 12 | power chords | doublés sur les voies 2 et 3 ; 2xx/1xx en alternance = vibrato |
| 4 | vide | sert à couper une voie |

Pièges : un même sample peut jouer deux lignes différentes sur deux voies (lead en harmonie) ; une voie peut changer
de rôle d'un pattern à l'autre (voie 4 = basse, puis lead aux patterns 27 à 29).

## Étape 2 : la fiche du morceau (`songs/<nom>.json`)

En plus des instruments du remaster, deux sections :

```json
"partitions": {
  "Guitare 1 (lead)":      {"instrument": "guitare", "samples": [5], "lead": true},
  "Guitare 2 (rythmique)": {"instrument": "guitare", "samples": [5, 11, 12]},
  "Basse":                 {"instrument": "basse", "samples": [3]},
  "Batterie (version enrichie)": {"instrument": "batterie", "samples": [1, 2], "extras": true}
},
"piano": {"melody": "Guitare 1 (lead)", "chords": [12, 10], "riff": [11], "bass": [3]}
```

- `partitions` : une entrée par musicien, **dans l'ordre de priorité**. Chaque attaque va à la première partie qui
  l'accepte. `"lead": true` : la partie ne prend, à chaque mesure, que la voie qui joue le plus haut parmi ses
  samples ; les autres lignes du même sample tombent dans la partie suivante qui le liste (ici la guitare 2, d'où
  le 5 dans ses samples). `"extras": true` : ajoute le charleston et les crashs de la version enrichie.
  `instrument` : `guitare`, `basse` ou `batterie`.
- `piano` : `melody` = nom d'une partie ci-dessus ; `chords` = samples qui donnent l'harmonie, **le premier passe
  avant** (la guitare avant le chœur) ; `riff` = samples joués piqués à la main gauche ; `bass` = la basse.
  Réglages facultatifs : `dense` (8), `soundfont`, `loudness` (−16), `reverb` (voir `DEFAULTS` dans `piano.py`).

Ce qui compte aussi dans la fiche des instruments : `chord` (le power chord `[0, 7, 12]` donne trois notes dans la
tablature), `max_length` ≤ 0,2 s (= note étouffée, écrite P.M.), `drum` (note de batterie GM).

## Étape 3 : les tablatures (`remaster/partitions.py`)

Pour chaque partie : `score.events()` regroupe les attaques par ligne (accords) ; une note dure jusqu'à la suivante
de la même partie (un guitariste ne tient pas une note sous la suivante).

**Placement sur le manche** (`remaster/fretboard.py`) :
1. toutes les positions possibles d'une note ou d'un accord : une note par corde, case 0 à 22 (20 à la basse),
   4 cases d'écart au plus entre doigts ;
2. un coût par position : 0,08 par case (rester bas), +0,4 par case au-delà de la 12e, **+2,5 par corde sautée**
   dans un accord, +1,5 pour une corde à vide mêlée à des notes appuyées ;
3. un coût de déplacement : l'écart de position de la main d'un accord au suivant ;
4. la suite la moins chère sur tout le morceau (programmation dynamique, algorithme de Viterbi).

Sans les deux pénalités du point 2, la première version donnait des quintes à cordes sautées (ré 2 + si à vide) :
jouable mais personne ne joue comme ça. Avec elles : formes standard (0-2-2 en mi ouvert, 2-4 sur ré-sol…).

- Note trop grave pour l'instrument (sous le mi grave) : montée d'une octave, comptée dans le message affiché.
- Accord injouable (souvent deux voies du module qui jouent deux accords à la fois) : on enlève d'abord les doublures
  d'octave, puis les notes du milieu, puis la basse, jusqu'à ce qu'il tienne sur le manche ; compté aussi.
  *Dr Mario* : 40 notes remontées et 24 enlevées sur 1 599 à la guitare 2.

**Textes au-dessus de la portée** (`score.bend_marks`, d'après la hauteur à la fin de chaque ligne, arrondie au
demi-ton) :

| Mouvement de la hauteur pendant la note | Texte |
|---|---|
| monte de 1 à 2 demi-tons sur une note seule | « b. ½ » / « b. 1 » (bend), puis « lâcher » si elle revient |
| monte de 3 demi-tons ou plus, ou accord qui monte | « gliss. » |
| descend puis remonte (alternance 2xx / 1xx) | « vibr. » |
| descend sans revenir | « gliss. » |

**P.M.** : une suite de notes étouffées (moins de 8 lignes entre deux) reçoit « P.M. - - - » en pointillé ; les
accords ouverts au milieu de la suite sont accentués (>). La légende de chaque PDF n'explique que les signes présents.

**Batterie** : deux voix, les mains (hampes en haut : caisse claire, charleston, crash) et la grosse caisse (en bas).
Un coup dure jusqu'au coup suivant de la même voix (une noire au plus), jamais lié. Le charleston et les crashs
reprennent exactement les règles de `extras.py` (`hihat_rows`, `crash_rows`).

## Étape 4 : le piano (`remaster/piano.py`)

1. **Mélodie** (main droite, hampes en haut) : la partie `melody`. Un bend tenu au moins deux lignes devient une
   nouvelle note à la hauteur atteinte (le piano ne tire pas de corde). Une partie (repère) dont la mélodie est en
   moyenne sous le mi 4 monte d'une octave ; une note isolée sous le sol 3 aussi.
2. **Harmonie** : un changement d'accord à chaque attaque d'un sample `chords` (fondamentale = sa note la plus
   grave ; le premier sample listé passe avant). Mesures sans accord : la basse donne la fondamentale.
3. **Tierce** : les guitares jouent des quintes, sans tierce. Tonalité de chaque partie (profils de
   Krumhansl-Kessler sur la partie, celle d'avant et celle d'après) ; tierce = celle que chante la mélodie pendant
   l'accord, sinon celle de la gamme. *Dr Mario* : mi mineur → mi mineur, ré majeur, do majeur, si mineur, fa majeur.
4. **Accords** (main droite, hampes en bas) : trois sons serrés (dans l'octave), la note du haut **sous** la note la
   plus grave de la mélodie qui sonne en même temps (notes tenues comprises), proches de l'accord précédent. Pas
   d'accords sous une mélodie de plus de 8 notes par mesure. Dans les riffs : un accord par attaque, une noire au plus,
   sauf si la note du module dure plus d'une demi-mesure (nappe de chœur, tenue).
5. **Main gauche** : si la guitare étouffée (`riff`) joue dans la mesure, le riff une octave plus bas (entre do 2 et
   si 2), piqué, avec l'octave sur les accords ; sinon la basse en octaves (entre sol 1 et fa# 2), une attaque par
   temps quand elle répète la même note ; sinon la fondamentale en octave, tenue.
6. **Pédale** : changée à chaque accord, sauf dans les mesures de riff (son sec). Écrit « Péd. » / « sans Péd. ».
7. **Son** : MIDI (nuances 54 à 82, un peu d'humanisation : ±3 de force, ±6 ms) → FluidSynth avec le
   **Salamander Grand Piano V3** (SF2 FreePats, Yamaha C5, 16 nuances, CC-BY : citer Alexander Holm) →
   **Dragonfly Hall** (sec 80 %, salle de 26 m, 1,9 s) → MP3 320 kbit/s à −16 LUFS (un piano seul à −14 serait trop
   compressé).

## Étape 5 : vérifier

- **Messages de la commande** : notes remontées, notes enlevées. Beaucoup d'enlevées = revoir la répartition des
  samples dans `partitions`.
- **Les pages** : `scripts/preview_pages.py` → `out\<Jeu>\<nom>\partitions\apercu\*.png`. Claude les regarde une par une
  (il ne lit pas un PDF page à page). À regarder : doigtés (cordes voisines, pas de saut de 10 cases), pauses
  regroupées, P.M., accords sous la mélodie, pas de note piquée liée.
- **Le MP3 du piano** : durée = celle du module + 3 s de réverbération ; niveau −16 LUFS ; crête −1,5 dB ; aucun
  trou. Puis **l'oreille de l'utilisateur**, seule vraie validation.
- **Tests** : `tests/test_partitions.py` (durées, noms de notes, manche, grille, parties, bends, mesures complètes,
  arrangement, tierces, gravure). Ils sont écrits pour *Dr Mario* : pour un autre module, copier les tests de grille
  et de parties avec ses valeurs.

## Pièges LilyPond rencontrés (déjà réglés dans `remaster/lily.py`)

- **Numéro de corde d'une note seule** : `e'\1` placé avant la durée se lit « corde 14 » si on écrit `e'\14`. Il faut
  `e'4\1` (durée d'abord). Dans un accord, pas de problème : `<e\5 b\4>8`. Le code met `{d}` à la place de la durée.
- **Pauses de plusieurs mesures** : `\compressEmptyMeasures` ne regroupe que `R1*12` écrit d'un bloc, et seulement si
  **aucune autre voix de la portée** ne coupe la suite : la voix invisible des textes doit elle aussi écrire `s1*12`,
  pas `s1 s1 s1…` (`Context.join_bars`).
- **P.M. en pointillé** : `\startTextSpan` / `\stopTextSpan` sur les silences invisibles de la voix des textes ;
  impossible de commencer et finir sur la même ligne (une seule note étouffée → simple texte « P.M. »).
- **Liaisons d'une mesure à l'autre** : à indiquer explicitement (5e élément des notes de `bar_music`).
- **Découpage des durées** (`lily.split`) : une valeur doit respecter les temps (noire sur un temps, blanche sur le 1er
  ou le 3e…), sinon deux valeurs liées. Ne jamais dépasser la barre de mesure (sinon boucle sans fin : bug corrigé).
- **Deux voix au piano** : des voix nommées et permanentes (`mel`, `acc`), avec `s` (invisible) quand l'une se tait ;
  sinon les liaisons se perdent d'une mesure à l'autre.
- LilyPond tourne dans le dossier du fichier : lui passer des **chemins absolus**.
- La console Windows n'affiche pas « → » : les commandes passent la sortie en UTF-8.

## Ce qui se règle par morceau

- Qui joue quoi (`partitions`, `piano`), et l'ordre de priorité des parties.
- La grille si le module n'est pas en 16 lignes par mesure (aujourd'hui fixe : `score.ROWS_PER_BAR`).
- `dense` du piano si la mélodie est très rapide.
- Les tierces : si une harmonie sonne faux, regarder la tonalité estimée de la partie (`piano.section_keys`) ; on
  pourra ajouter une correction manuelle dans la fiche (pas encore fait).

## Idées pour la suite

Voir [ROADMAP.md](ROADMAP.md) : export Guitar Pro / MusicXML, noms d'accords, piano simplifié, batterie fidèle.
