#include "rb_espeak.h"
#include "engine/speak_lib.h"

#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static size_t sample_count;
static size_t nonzero_count;
static uint64_t pcm_hash;

static void require(int condition, const char *message)
{
    if (!condition)
    {
        fprintf(stderr, "FAIL Polish minus: %s\n", message);
        exit(1);
    }
}

static int receive(const short *samples, int count, void *context)
{
    (void)context;
    require(samples != NULL && count > 0 && count <= 441, "bounded PCM callback");
    for (int index = 0; index < count; ++index)
    {
        pcm_hash ^= (uint16_t)samples[index];
        pcm_hash *= UINT64_C(1099511628211);
        nonzero_count += samples[index] != 0;
    }
    sample_count += (size_t)count;
    return 0;
}

int main(int count, char **arguments)
{
    require(count == 3, "data parent and private trace path required");
    require(rb_espeak_init(arguments[1]) == 22050, "initialize supplied data");
    FILE *trace = fopen(arguments[2], "w+");
    require(trace != NULL, "open private trace");
    const int rates[] = {175, 451, 1350};
    const char *identifiers[] = {"punctuation", "character", "word"};
    for (size_t rate_index = 0; rate_index < sizeof(rates) / sizeof(rates[0]); ++rate_index)
    {
        for (size_t case_index = 0; case_index < sizeof(identifiers) / sizeof(identifiers[0]); ++case_index)
        {
            require(fseek(trace, 0, SEEK_END) == 0, "seek trace end");
            long start = ftell(trace);
            require(start >= 0, "trace position");
            espeak_SetPhonemeTrace(1, trace);
            sample_count = nonzero_count = 0;
            pcm_hash = UINT64_C(1469598103934665603);
            int result;
            if (case_index == 1)
                result = rb_espeak_synth_character('-', "pl", "", rates[rate_index],
                                                  50, 100, 50, 0, receive, NULL);
            else
                result = rb_espeak_synth(case_index == 0 ? "-" : "minus", "pl", "",
                                         rates[rate_index], 50, 100, 50, 0,
                                         RB_ESPEAK_PUNCT_ALL, receive, NULL);
            espeak_SetPhonemeTrace(0, NULL);
            require(result == RB_ESPEAK_OK, "synthesis completes");
            require(sample_count > 0 && nonzero_count > 0, "nonzero PCM");
            require(fflush(trace) == 0, "flush trace");
            long end = ftell(trace);
            char phonemes[4096];
            require(end > start && end - start < (long)sizeof(phonemes), "bounded phoneme trace");
            require(fseek(trace, start, SEEK_SET) == 0, "rewind trace segment");
            size_t length = fread(phonemes, 1, (size_t)(end - start), trace);
            require(length == (size_t)(end - start) && !ferror(trace), "read trace");
            phonemes[length] = '\0';
            for (size_t index = 0; index < length; ++index)
                if (phonemes[index] == '\n' || phonemes[index] == '\r' || phonemes[index] == '\t')
                    phonemes[index] = ' ';
            require(strstr(phonemes, "m'inus") != NULL, "supplied minus pronunciation");
            printf("%s\t%d\t%zu\t%" PRIu64 "\t%s\n", identifiers[case_index],
                   rates[rate_index], sample_count, pcm_hash, phonemes);
        }
    }
    require(fclose(trace) == 0, "close trace");
    puts("PASS: Polish minus, 9 actual phoneme and nonzero PCM cases");
    return 0;
}
