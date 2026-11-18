/* uade2wav : joue une musique Amiga avec UADE (émulateur des lecteurs Amiga) et l'enregistre en WAV.

   uade2wav <dossier de données UADE> <uadecore.exe> <musique> <sortie.wav> [sous-morceau] [secondes max] [journal]

   - journal : fichier où UADE écrit tout ce que le lecteur envoie à la puce son (période, volume, sample de chaque
     voie, et le son de chaque voie seule) : c'est de là qu'on tire les notes (remaster/paula.py) ;

   - sans sous-morceau (ou -1) : le sous-morceau par défaut ;
   - affiche « subsongs <cur> <min> <max> », « format <nom> », « player <nom> », puis « seconds <durée> » ;
   - la musique s'arrête à sa fin (si le lecteur la signale), après 5 s de silence, ou au bout de [secondes max]
     (défaut 600).
   Écrit pour Remaster AMIGA Music, sur le modèle de uadesimple (UADE, Heikki Orsila, GPL / domaine public).
*/
#include <uade/uade.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

static void put32(FILE *f, uint32_t v) { fputc(v & 255, f); fputc((v >> 8) & 255, f); fputc((v >> 16) & 255, f); fputc(v >> 24, f); }
static void put16(FILE *f, uint16_t v) { fputc(v & 255, f); fputc(v >> 8, f); }

static void wav_header(FILE *f, int rate, uint32_t bytes)
{
	fwrite("RIFF", 1, 4, f); put32(f, 36 + bytes); fwrite("WAVEfmt ", 1, 8, f);
	put32(f, 16); put16(f, 1); put16(f, 2); put32(f, rate); put32(f, rate * 4); put16(f, 4); put16(f, 16);
	fwrite("data", 1, 4, f); put32(f, bytes);
}

int main(int argc, char *argv[])
{
	if (argc < 5) {
		fprintf(stderr, "usage : uade2wav <donnees> <uadecore> <musique> <sortie.wav> [sous-morceau] [secondes]\n");
		return 2;
	}
	int subsong = argc > 5 ? atoi(argv[5]) : -1;
	const char *maxsec = argc > 6 ? argv[6] : "600";
	struct uade_config *uc = uade_new_config();
	uade_config_set_option(uc, UC_BASE_DIR, argv[1]);
	uade_config_set_option(uc, UC_UADECORE_FILE, argv[2]);
	uade_config_set_option(uc, UC_ONE_SUBSONG, NULL);
	uade_config_set_option(uc, UC_FREQUENCY, "48000");
	uade_config_set_option(uc, UC_TIMEOUT_VALUE, maxsec);
	uade_config_set_option(uc, UC_SUBSONG_TIMEOUT_VALUE, maxsec);
	uade_config_set_option(uc, UC_SILENCE_TIMEOUT_VALUE, "5");
	uade_config_set_option(uc, UC_NO_HEADPHONES, NULL);
	uade_config_set_option(uc, UC_PANNING_VALUE, "0.4");  /* Amiga : voies très séparées, on rapproche un peu */
	if (argc > 7)  /* journal de la puce son Paula (registres écrits par le lecteur + son de chaque voie) */
		uade_config_set_option(uc, UC_WRITE_AUDIO_FILE, argv[7]);
	struct uade_state *state = uade_new_state(uc);
	free(uc);
	if (state == NULL) {
		fprintf(stderr, "UADE : impossible de démarrer (dossier de données ?)\n");
		return 1;
	}
	int ret = uade_play(argv[3], subsong, state);
	if (ret <= 0) {
		fprintf(stderr, "UADE : format non reconnu ou lecture impossible\n");
		uade_cleanup_state(state);
		return 3;
	}
	const struct uade_song_info *info = uade_get_song_info(state);
	printf("subsongs %d %d %d\n", info->subsongs.cur, info->subsongs.min, info->subsongs.max);
	printf("format %s\nplayer %s\n", info->formatname, info->playername);
	fflush(stdout);
	int rate = uade_get_sampling_rate(state);
	FILE *f = fopen(argv[4], "wb");
	if (f == NULL) {
		uade_cleanup_state(state);
		return 4;
	}
	wav_header(f, rate, 0);
	uint32_t total = 0;
	char buf[8192];
	for (;;) {
		ssize_t n = uade_read(buf, sizeof buf, state);
		if (n <= 0)
			break;
		fwrite(buf, 1, n, f);
		total += n;
	}
	fseek(f, 0, SEEK_SET);
	wav_header(f, rate, total);
	fclose(f);
	printf("seconds %.2f\n", total / (4.0 * rate));
	uade_cleanup_state(state);
	return 0;
}
