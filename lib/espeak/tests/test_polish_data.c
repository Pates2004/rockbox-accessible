#include "rb_espeak.h"
#include "engine/speak_lib.h"

#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#endif

static uint64_t pcm_hash;
static size_t sample_count;
static size_t nonzero_count;

static void require(int condition, const char *message)
{
    if (!condition)
    {
        fprintf(stderr, "FAIL Polish data: %s\n", message);
        exit(1);
    }
}

static int receive(const short *samples, int count, void *context)
{
    (void)context;
    require(count > 0 && count <= 441, "bounded PCM callback");
    for (int index = 0; index < count; ++index)
    {
        pcm_hash ^= (uint16_t)samples[index];
        pcm_hash *= UINT64_C(1099511628211);
        nonzero_count += samples[index] != 0;
    }
    sample_count += count;
    return 0;
}

static int run_tests(int count, char **arguments)
{
    require(count == 2 || count == 3 || count == 5, "list or data parent, trace path and optional case/rate");
    const struct {
        const char *identifier;
        const char *language;
        const char *text;
    } cases[] = {
        {"singer", "pl", "singer"},
        {"singera", "pl", "singera"},
        {"singerem", "pl", "singerem"},
        {"singerowi", "pl", "singerowi"},
        {"singing", "pl", "singing"},
        {"singingu", "pl", "singingu"},
        {"ziscic", "pl", "ziścić"},
        {"zisci", "pl", "ziści"},
        {"ziscil", "pl", "ziścił"},
        {"ziscila", "pl", "ziściła"},
        {"ziscilo", "pl", "ziściło"},
        {"ziscili", "pl", "ziścili"},
        {"ziscily", "pl", "ziściły"},
        {"zisc", "pl", "ziść"},
        {"ziscmy", "pl", "ziśćmy"},
        {"zisccie", "pl", "ziśćcie"},
        {"ziszczac", "pl", "ziszczać"},
        {"ziszcza", "pl", "ziszcza"},
        {"ziszczony", "pl", "ziszczony"},
        {"ziszczenie", "pl", "ziszczenie"},
        {"ziszczenia", "pl", "ziszczenia"},
        {"ziszczeniu", "pl", "ziszczeniu"},
        {"singiel", "pl", "singiel"},
        {"singla", "pl", "singla"},
        {"singlowy", "pl", "singlowy"},
        {"singlem", "pl", "singlem"},
        {"singel", "pl", "singel"},
        {"singapur", "pl", "Singapur"},
        {"singapurski", "pl", "singapurski"},
        {"singularny", "pl", "singularny"},
        {"singularnosc", "pl", "singularność"},
        {"siny", "pl", "siny"},
        {"sinus", "pl", "sinus"},
        {"silikon", "pl", "silikon"},
        {"sitko", "pl", "sitko"},
        {"zima", "pl", "zima"},
        {"zimno", "pl", "zimno"},
        {"zielony", "pl", "zielony"},
        {"ziarno", "pl", "ziarno"},
        {"zidentyfikowac", "pl", "zidentyfikować"},
        {"zignorowac", "pl", "zignorować"},
        {"zintegrowac", "pl", "zintegrować"},
        {"druciana", "pl", "druciana"},
        {"policja", "pl", "policja"},
        {"english_singer", "en", "singer"},
        {"english_singing", "en", "singing"},
        {"english_singapore", "en", "Singapore"},
        {"english_dream", "en", "The dream came true."},
    };
    if (count == 2)
    {
        require(strcmp(arguments[1], "--list") == 0, "case list argument");
        for (size_t index = 0; index < sizeof(cases) / sizeof(cases[0]); ++index)
            puts(cases[index].identifier);
        return 0;
    }
    require(rb_espeak_init(arguments[1]) == 22050, "initialize supplied data");
#ifndef RB_ESPEAK_DATA_NATIVE
#ifdef _WIN32
    wchar_t trace_path[4096];
    require(MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, arguments[2], -1,
                               trace_path, 4096) > 0, "decode trace path");
    FILE *trace = _wfopen(trace_path, L"w+b");
#else
    FILE *trace = fopen(arguments[2], "w+");
#endif
    require(trace != NULL, "open phoneme trace");
#endif
    const int rates[] = {175, 451, 1350};
    int completed = 0;
    for (size_t index = 0; index < sizeof(cases) / sizeof(cases[0]); ++index)
        for (size_t rate = 0; rate < sizeof(rates) / sizeof(rates[0]); ++rate)
        {
            if (count == 5 && (strcmp(arguments[3], cases[index].identifier) != 0
                              || atoi(arguments[4]) != rates[rate]))
                continue;
#ifndef RB_ESPEAK_DATA_NATIVE
            require(fseek(trace, 0, SEEK_END) == 0, "seek trace end");
            long start = ftell(trace);
            require(start >= 0, "trace start");
            espeak_SetPhonemeTrace(1, trace);
#endif
            pcm_hash = UINT64_C(1469598103934665603);
            sample_count = nonzero_count = 0;
            require(rb_espeak_synth(cases[index].text, cases[index].language, "", rates[rate],
                                   50, 100, 50, 0, RB_ESPEAK_PUNCT_NONE, receive, NULL) == 0,
                    "synthesis succeeds");
            require(sample_count && nonzero_count, "nonzero PCM");
            char phonemes[4096] = "-";
#ifndef RB_ESPEAK_DATA_NATIVE
            espeak_SetPhonemeTrace(0, NULL);
            require(fflush(trace) == 0 && sample_count && nonzero_count, "nonzero PCM");
            long end = ftell(trace);
            require(end > start && end - start < (long)sizeof(phonemes), "bounded phoneme trace");
            require(fseek(trace, start, SEEK_SET) == 0, "rewind trace segment");
            size_t length = fread(phonemes, 1, (size_t)(end - start), trace);
            require(length == (size_t)(end - start) && !ferror(trace), "read trace segment");
            phonemes[length] = 0;
            for (size_t character = 0; character < length; ++character)
                if (phonemes[character] == '\n' || phonemes[character] == '\r' || phonemes[character] == '\t')
                    phonemes[character] = ' ';
#endif
            printf("%s\t%s\t%d\t%zu\t%" PRIu64 "\t%s\n", cases[index].identifier,
                   cases[index].language, rates[rate], sample_count, pcm_hash, phonemes);
            ++completed;
        }
#ifndef RB_ESPEAK_DATA_NATIVE
    require(fclose(trace) == 0, "close trace");
#endif
    require(completed == (count == 5 ? 1 : 144), "complete selected cases");
    return 0;
}

#ifdef _WIN32
int wmain(int count, wchar_t **wide_arguments)
{
    require(count == 2 || count == 3 || count == 5, "case list or data test arguments");
    char converted[5][4096];
    char *arguments[5];
    for (int index = 0; index < count; ++index)
    {
        require(WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, wide_arguments[index], -1,
                                   converted[index], 4096, NULL, NULL) > 0, "UTF-8 argument");
        arguments[index] = converted[index];
    }
    return run_tests(count, arguments);
}
#else
int main(int count, char **arguments)
{
    return run_tests(count, arguments);
}
#endif
