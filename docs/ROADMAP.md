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

## Musiques à lecteur intégré (TFMX, David Whittaker…)

Fait le 18/11/2026 : UADE construit dans tools\uade (modifié pour écrire le journal de la puce son et copier les
samples), les originaux enregistrés en MP3 (une fois la boucle, deux si elle fait moins de 2 min), et remaster
possible (`python -m remaster <fichier> --sous-morceau N`), vérifié note pour note sur Dr Mario.

À faire :
- **Partitions** de ces musiques : déduire la grille (tempo, lignes, mesures) des instants des notes — le lecteur
  avance par trames de 20 ms ; chercher le pas régulier (souvent 3 à 8 trames par ligne) et la mesure (caisse claire).
- **Fiches d'instruments** : pour chaque jeu, reconnaître les samples (batterie, basse, lead…) comme pour Dr Mario.
- Rick Dangerous (`cust.`) : UADE ne le reconnaît pas ; la version alternative est abîmée dans l'archive.

## Ensuite

- **Écoute rapide** : un extrait de 20 s rendu en quelques secondes, pour comparer deux réglages.
- **Appli PC** (voir `IDEES-APPLIS.md`, idée 3) : liste des samples, « Écouter l'original », choix de l'instrument
  (liste déroulante), « Écouter le remplaçant », puis « Créer le MP3 ».
- **Batterie enrichie plus variée** : ride, toms de transition, ouverture du charleston.
- **Lecteur SFZ** : filtres, LFO, notes de relâchement ; banques qui ne passent pas encore (DRSKit de DrumGizmo :
  variables `$v61h` non résolues).
