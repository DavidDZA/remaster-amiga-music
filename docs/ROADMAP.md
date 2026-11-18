# Roadmap

## À faire en priorité : de vrais VST, choisis à l'oreille (« option 1 »)

Décidé le 17/11/2026 : l'utilisateur veut passer aux VST gratuits de qualité, mais n'a pas eu le temps de les
installer. **À faire dès que possible.**

Pourquoi : le rendu actuel est fait sans oreilles (Claude ne peut pas écouter). Retour du 17/11 sur la v2 : guitares
nasillardes, kick inaudible, impression d'écho permanent et de flou, « difficile à écouter ». Un bon VST arrive avec des
presets réglés par des gens qui écoutent, et l'utilisateur peut choisir le son lui-même.

Principe :
1. L'utilisateur installe quelques VST3 gratuits (parfois un compte, un e-mail ou un code au premier lancement) :
   - batterie : **MT Power Drum Kit 2** (Manda Audio, kit rock, VST3, gratuit avec demandes de don) ;
   - ampli métal : **Ignite Amps Emissary + NadIR** (baffles), ou **ML Sound Lab Amped Roots Free** ;
   - basse : un VSTi de basse gratuit (Ample Bass P Lite II, à vérifier), ou la banque SFZ actuelle + un ampli basse ;
   - guitare : les VSTi de guitare électrique gratuits sont rares (Shreddage *Free* demande Kontakt Player) ; garder
     les guitares DI échantillonnées et ne changer que l'ampli, sauf meilleure trouvaille.
2. L'outil ouvre la **fenêtre du VST** (`plugin.show_editor()` de Pedalboard) : l'utilisateur choisit un preset en
   écoutant, l'outil enregistre l'état du plugin (`raw_state`) dans la fiche du morceau (`songs/<nom>.json` ou un
   fichier à côté).
3. Le rendu rejoue ensuite ce VST avec cet état : `"type": "vst"` dans `fx` (déjà en place pour les effets), et un
   nouveau moteur `"vsti"` pour les instruments (Pedalboard joue un instrument VST3 à partir de messages MIDI).
4. Les VST3 restent dans `tools/` si l'installeur le permet (dossier personnalisé), sinon dans
   `C:\Program Files\Common Files\VST3` (le chargeur les cherche aux deux endroits).

## Fait le 18/11/2026 : partitions et piano

Tablatures (2 guitares, basse), batterie de la version enrichie, arrangement pour piano seul (MP3 + PDF). À écouter
et relire par l'utilisateur : doigtés, choix des tierces au piano, son du piano (rien n'a été validé à l'oreille).

Pistes : exporter aussi en **Guitar Pro** / **MusicXML** (pour TuxGuitar, MuseScore, Songsterr) ; noms d'accords
(E5, D5…) au-dessus de la guitare rythmique ; une partition piano simplifiée (niveau débutant) ; batterie fidèle
(sans les ajouts) sur demande.

## Autres formats de musique Amiga

L'import des archives .lha (18/11/2026) a laissé de côté 50 jeux sans module ProTracker. Fichiers trouvés, par
format : `smp`/`rjp` Richard Joseph (55), `cust` lecteurs maison (36), `med` OctaMED (29), `sjs` (25), `pap` (22),
`dw` David Whittaker (18), `p4x` The Player 4 (17), `mdat`/`smpl` TFMX (28), `jd` (12)…
Pistes : convertir en .mod ce que sait lire OpenMPT (OctaMED, The Player 4, XM…) ; pour les formats à lecteur
intégré (TFMX, Richard Joseph, David Whittaker, `cust`), passer par UADE pour en tirer les notes.

## Ensuite

- **Écoute rapide** : un extrait de 20 s rendu en quelques secondes, pour comparer deux réglages.
- **Appli PC** (voir `IDEES-APPLIS.md`, idée 3) : liste des samples, « Écouter l'original », choix de l'instrument
  (liste déroulante), « Écouter le remplaçant », puis « Créer le MP3 ».
- **Autres formats** : `.xm`, `.s3m`, `.it`.
- **Batterie enrichie plus variée** : ride, toms de transition, ouverture du charleston.
- **Lecteur SFZ** : filtres, LFO, notes de relâchement ; banques qui ne passent pas encore (DRSKit de DrumGizmo :
  variables `$v61h` non résolues).
