#include "rb_espeak.h"
#include "engine/speak_lib.h"

#include <limits.h>
#include <locale.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <windows.h>
#include <fcntl.h>
#include <io.h>
#endif

struct capture {
    uint64_t samples;
    uint64_t checksum;
    int blocks;
    int nonzero;
    int abort_after;
    int check_reentry;
    int word_count;
    int word_positions[64];
    int word_times[64];
};

static int record_pcm;

static void require(int condition, const char *message)
{
    if (!condition) {
        fprintf(stderr, "FAIL: %s\n", message);
        exit(1);
    }
}

static int capture_pcm(const short *samples, int count, void *user)
{
    struct capture *capture = user;
    require(samples != NULL && count > 0 && count <= 441, "PCM callback bounds");
    if (record_pcm)
        require(fwrite(samples, sizeof(*samples), count, stdout) == (size_t)count,
                "write PCM regression stream");
    capture->samples += count;
    capture->blocks++;
    for (int index = 0; index < count; ++index) {
        capture->nonzero |= samples[index] != 0;
        capture->checksum = capture->checksum * 33 + (uint16_t)samples[index];
    }
    if (capture->check_reentry) {
        capture->check_reentry = 0;
        require(rb_espeak_validate_voice("pl", "m3") == RB_ESPEAK_OK,
                "read-only validation during synthesis");
        require(rb_espeak_voice_count(true) == 105, "immutable variants during synthesis");
        require(rb_espeak_synth("test", "pl", "", 175, 50, 100, 50, 0, RB_ESPEAK_PUNCT_NONE,
                               capture_pcm, user) == RB_ESPEAK_BUSY, "reject recursive synthesis");
    }
    return capture->abort_after && capture->blocks >= capture->abort_after;
}

static void capture_position(int character, int milliseconds, void *user)
{
    struct capture *capture = user;
    fprintf(stderr, "word event character=%d time=%d\n", character, milliseconds);
    require(character > 0 && milliseconds >= 0, "valid word event");
    require(capture->word_count < 64, "bounded word event fixture");
    if (capture->word_count)
        require(milliseconds >= capture->word_times[capture->word_count - 1],
                "monotonic word event times");
    capture->word_positions[capture->word_count] = character;
    capture->word_times[capture->word_count++] = milliseconds;
}

static void test_word_positions(void)
{
    struct capture capture = {0};
    require(rb_espeak_synth_tracked("\xc4\x85 b c", "pl", "", 175, 50, 100, 50, 0,
            RB_ESPEAK_PUNCT_NONE, capture_pcm, capture_position, &capture) == RB_ESPEAK_OK,
            "tracked synthesis");
    require(capture.word_count == 3, "one event per fixture word");
    require(capture.word_positions[0] == 1 && capture.word_positions[1] == 3 &&
            capture.word_positions[2] == 5, "one-based Unicode character positions");
    require(capture.word_times[2] > capture.word_times[0] &&
            (uint64_t)capture.word_times[2] * 22050 / 1000 < capture.samples,
            "word events inside actual PCM duration");
    fprintf(stderr, "PASS: native word events map Unicode characters to PCM time\n");
    const char *texts[] = { "Zażółć, gęślą! Drugi wiersz.\nTrzeci?", "Ąla ma kota.",
                           "(first) [second] {third} -- fourth..." };
    for (size_t index = 0; index < sizeof(texts) / sizeof(texts[0]); ++index)
        for (int punctuation = RB_ESPEAK_PUNCT_NONE;
             punctuation <= RB_ESPEAK_PUNCT_ALL; ++punctuation) {
            memset(&capture, 0, sizeof(capture));
            require(rb_espeak_synth_tracked(texts[index], index == 2 ? "en" : "pl", "",
                        175, 50, 100, 50, 0, punctuation, capture_pcm,
                        capture_position, &capture) == RB_ESPEAK_OK, "punctuated tracked synthesis");
            int characters = 0;
            for (const unsigned char *byte = (const unsigned char *)texts[index]; *byte; ++byte)
                if ((*byte & 0xc0) != 0x80)
                    ++characters;
            require(capture.word_count > 0, "punctuated fixture emits word events");
            for (int word = 0; word < capture.word_count; ++word)
                require(capture.word_positions[word] <= characters,
                        "punctuated event remains within original text");
        }
}

static void test_character_speech(void)
{
    const unsigned int characters[] = { 'a', 0x105, '.', '!', ' ', '\t', '\n', 0x1f600 };
    const char *languages[] = { "pl", "en" };
    for (size_t language = 0; language < sizeof(languages) / sizeof(languages[0]); ++language)
        for (size_t index = 0; index < sizeof(characters) / sizeof(characters[0]); ++index) {
            struct capture capture = {0};
            require(rb_espeak_synth_character(characters[index], languages[language], "",
                        175, 50, 100, 50, 0, capture_pcm, &capture) == RB_ESPEAK_OK,
                    "native character synthesis succeeds");
            fprintf(stderr, "character U+%04x language=%s samples=%llu nonzero=%d\n",
                    characters[index], languages[language],
                    (unsigned long long)capture.samples, capture.nonzero);
            require(capture.nonzero, "native character has audible name or fallback");
        }
}

static struct capture speak(const char *text, const char *language, const char *variant,
                            int rate, int pitch, int volume, int range, int wordgap)
{
    struct capture capture = {0};
    require(rb_espeak_synth(text, language, variant, rate, pitch, volume, range, wordgap, RB_ESPEAK_PUNCT_NONE,
                           capture_pcm, &capture) == RB_ESPEAK_OK, "synthesis status");
    require(capture.samples > 0, "produced PCM samples");
    if (record_pcm)
        fprintf(stderr, "PCM language=%s variant=%s rate=%d pitch=%d volume=%d range=%d wordgap=%d samples=%llu hash=%llu\n",
                language, variant, rate, pitch, volume, range, wordgap,
                (unsigned long long)capture.samples, (unsigned long long)capture.checksum);
    return capture;
}

static FILE *open_trace(const char *output_directory, const char *filename);

static void test_text_prefixes(const char *output_directory)
{
    static const struct {
        const char *language;
        const char *text;
    } cases[] = {
        {"tr", "Ankara'nın Türkiye'nin İstanbul'da"},
        {"tr", "Ankara'nın"},
        {"tr", "Türkiye'nin"},
        {"tr", "İstanbul'da"},
        {"tr", "Ankara'dan İzmir'e Çanakkale'nin Afyonkarahisar'ın"},
        {"tr", "Çiçekler büyüyor. Bugün saat 12, yarın 23."},
        {"de", "Unwiederbringlich wiederherstellen und unterscheiden."},
        {"hu", "Budapest szép város. Egy, kettő, három."},
        {"pl", "Druciana bociana bocianem bocianowi starcia tarcia natarcia."},
        {"pl", "Zażółć gęślą jaźń. Pierwszy plik, 12 katalogów, 345 utworów."},
        {"en", "Undo, redo and reassemble. First file, 12 folders, 345 songs."},
    };
    for (int rate = 175; rate <= 450; rate += 275) {
        for (size_t index = 0; index < sizeof(cases) / sizeof(cases[0]); ++index) {
            struct capture result = speak(cases[index].text, cases[index].language, "",
                                          rate, 50, 100, 50, 0);
            require(result.nonzero && result.samples > 0, "ordinary prefix text emits PCM");
            fprintf(stderr, "prefix case=%zu language=%s rate=%d samples=%llu checksum=%llu\n",
                    index, cases[index].language, rate,
                    (unsigned long long)result.samples, (unsigned long long)result.checksum);
        }
    }
    // Long ordinary filenames preserve their complete UTF-8 stem when a
    // Turkish suffix follows the apostrophe. Cover the former 41-byte buffer
    // and the former six-bit length decoder with actual synthesis and traces.
    static const char *stems[] = {
        "istanbultekniküniversitesikütüphanesi",
        "türkiyecumhuriyetikültürveturizmbakanlığıkütüphanelerveyayımlargenelmüdürlüğü",
    };
    FILE *trace = open_trace(output_directory, "text-prefix-trace.txt");
    for (size_t index = 0; index < sizeof(stems) / sizeof(stems[0]); ++index) {
        char text[256];
        char expected[256];
        require(strlen(stems[index]) > (index ? 63u : 39u), "long UTF-8 stem fixture");
        require(snprintf(text, sizeof(text), "%s'nin", stems[index]) > 0,
                "format ordinary suffixed filename");
        require(snprintf(expected, sizeof(expected), "Translate '%s'", stems[index]) > 0,
                "format complete stem trace");
        require(fseek(trace, 0, SEEK_END) == 0, "seek prefix trace end");
        long start = ftell(trace);
        require(start >= 0, "prefix trace position");
        espeak_SetPhonemeTrace(2, trace);
        struct capture result = speak(text, "tr", "", 175, 50, 100, 50, 0);
        espeak_SetPhonemeTrace(0, NULL);
        require(result.nonzero, "long suffixed filename has non-silent PCM");
        require(fflush(trace) == 0 && fseek(trace, start, SEEK_SET) == 0,
                "read prefix trace segment");
        int found = 0;
        char line[1024];
        while (fgets(line, sizeof(line), trace))
            found |= strstr(line, expected) != NULL;
        require(!ferror(trace) && found, "whole UTF-8 prefix is retranslated without truncation");
        clearerr(trace);
    }
    require(fclose(trace) == 0, "close prefix trace");
    fprintf(stderr, "PASS: ordinary prefix text, language switches and numbers\n");
}

static FILE *open_trace(const char *output_directory, const char *filename)
{
    char path[1024];
    require(snprintf(path, sizeof(path), "%s/%s", output_directory, filename) < (int)sizeof(path),
            "trace path length");
#ifdef _WIN32
    wchar_t wide_path[1024];
    require(MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1,
                               wide_path, 1024) > 0, "decode trace path");
    FILE *trace = _wfopen(wide_path, L"w+");
#else
    FILE *trace = fopen(path, "w+");
#endif
    require(trace != NULL, "open phoneme trace");
    return trace;
}

static void test_polish_trace(const char *output_directory)
{
    FILE *trace = open_trace(output_directory, "polish-ci.txt");
    espeak_SetPhonemeTrace(1, trace);
    speak("druciana bociana bocianem bocianowi starcia tarcia natarcia druciany tarciem policja Alicia",
          "pl", "", 175, 50, 100, 50, 0);
    espeak_SetPhonemeTrace(0, NULL);
    rewind(trace);
    char phonemes[8192];
    size_t length = fread(phonemes, 1, sizeof(phonemes) - 1, trace);
    phonemes[length] = 0;
    fclose(trace);
    const char *required[] = {
        "dRuts;'ana", "bOts;'ana", "bOts;'anEm", "b,Ots;an'Ovi", "st'aRts;a",
        "t'aRts;a", "nat'aRts;a", "dRuts;'any", "t'aRts;Em", "pOl'itsja", "al'isja"
    };
    for (size_t index = 0; index < sizeof(required) / sizeof(required[0]); ++index)
        require(strstr(phonemes, required[index]) != NULL, required[index]);
    require(strstr(phonemes, "dRusj") == NULL && strstr(phonemes, "bOsj") == NULL,
            "ci must not become si");
}

static int direct_pcm(short *samples, int count, espeak_EVENT *events)
{
    (void)events;
    if (samples)
        require(count >= 0 && count <= 1102, "50 ms PCM sample count");
    return 0;
}

static struct capture *native_capture;

static int capture_native(short *samples, int count, espeak_EVENT *events)
{
    (void)events;
    if (!samples || count == 0)
        return 0;
    return capture_pcm(samples, count, native_capture);
}

struct punctuation_capture {
    struct capture audio;
    char phonemes[8192];
};

static struct punctuation_capture speak_punctuation(const char *text, const char *language,
                                                    int punctuation, int native, FILE *trace)
{
    struct punctuation_capture result = {0};
    long trace_start = ftell(trace);
    require(trace_start >= 0, "punctuation trace position");
    espeak_SetPhonemeTrace(1, trace);
    if (native) {
        const wchar_t *lists[] = {L"", L".,;:!?", L".,;:!?\"'()[]{}-", L""};
        int modes[] = {espeakPUNCT_NONE, espeakPUNCT_SOME, espeakPUNCT_SOME, espeakPUNCT_ALL};
        require(espeak_SetVoiceByName(language) == EE_OK, "native punctuation voice");
        require(espeak_SetParameter(espeakRATE, 175, 0) == EE_OK, "native rate");
        require(espeak_SetParameter(espeakPITCH, 50, 0) == EE_OK, "native pitch");
        require(espeak_SetParameter(espeakVOLUME, 100, 0) == EE_OK, "native volume");
        require(espeak_SetParameter(espeakRANGE, 50, 0) == EE_OK, "native pitch range");
        require(espeak_SetParameter(espeakWORDGAP, 0, 0) == EE_OK, "native word gap");
        require(espeak_SetPunctuationList(lists[punctuation]) == EE_OK, "native punctuation list");
        require(espeak_SetParameter(espeakPUNCTUATION, modes[punctuation], 0) == EE_OK,
                "native punctuation mode");
        native_capture = &result.audio;
        require(espeak_Synth(text, strlen(text) + 1, 0, POS_CHARACTER, 0,
                             espeakCHARS_UTF8 | espeakENDPAUSE, NULL, NULL) == EE_OK,
                "native punctuation synthesis");
        native_capture = NULL;
    } else {
        require(rb_espeak_synth(text, language, "", 175, 50, 100, 50, 0, punctuation,
                               capture_pcm, &result.audio) == RB_ESPEAK_OK,
                "backend punctuation synthesis");
    }
    espeak_SetPhonemeTrace(0, NULL);
    require(result.audio.samples > 0 && result.audio.nonzero, "punctuation produces nonzero PCM");
    require(fflush(trace) == 0, "flush punctuation trace");
    long trace_end = ftell(trace);
    require(trace_end > trace_start && trace_end - trace_start < (long)sizeof(result.phonemes),
            "punctuation trace bounds");
    require(fseek(trace, trace_start, SEEK_SET) == 0, "seek to punctuation trace");
    size_t length = fread(result.phonemes, 1, (size_t)(trace_end - trace_start), trace);
    require(!ferror(trace) && length > 0, "read punctuation phonemes");
    result.phonemes[length] = 0;
    require(fseek(trace, trace_end, SEEK_SET) == 0, "resume punctuation trace output");
    return result;
}

static void test_punctuation(int native, const char *output_directory)
{
    const char *languages[] = {"en", "pl"};
    const struct {
        const char *symbol;
        int first_announced;
    } cases[] = {
        {".", 1}, {",", 1}, {";", 1}, {":", 1}, {"!", 1}, {"?", 1},
        {"\"", 2}, {"'", 2}, {"(", 2}, {")", 2}, {"[", 2}, {"]", 2},
        {"{", 2}, {"}", 2}, {"-", 2}, {"_", 3}, {"|", 3},
        {"??", 1}, {"???", 1}, {"????", 1},
        {"/", 0}, {"\\", 0}, {"@", 0}, {"+", 0}, {"^", 0}, {"`", 0}, {"~", 0}, {"...", 0}
    };
    FILE *trace = open_trace(output_directory, native ? "punctuation-native-trace.txt" : "punctuation-trace.txt");
    for (size_t language = 0; language < sizeof(languages) / sizeof(languages[0]); ++language) {
        for (size_t index = 0; index < sizeof(cases) / sizeof(cases[0]); ++index) {
            char text[64];
            snprintf(text, sizeof(text), "test %s test", cases[index].symbol);
            struct punctuation_capture results[4];
            fprintf(stderr, "%s punctuation language=%s symbol=%s", native ? "native" : "backend",
                    languages[language], cases[index].symbol);
            for (int level = 0; level < 4; ++level) {
                results[level] = speak_punctuation(text, languages[language], level, native, trace);
                fprintf(stderr, " level%d=%llu/%llu", level, (unsigned long long)results[level].audio.samples,
                        (unsigned long long)results[level].audio.checksum);
            }
            fputc('\n', stderr);
            if (cases[index].first_announced) {
                for (int level = 1; level < 4; ++level) {
                    int announced = level >= cases[index].first_announced;
                    require((strcmp(results[0].phonemes, results[level].phonemes) != 0) == announced,
                            "punctuation list membership changes phonemes, not just noise");
                    if (announced) {
                        require(results[level].audio.samples > results[0].audio.samples + 2205,
                                "announcing punctuation adds more than 100 ms of real PCM");
                        require(results[level].audio.checksum != results[0].audio.checksum,
                                "announcing punctuation changes PCM samples");
                    }
                }
            }
        }
        const char *text = "test ? test ( test _ test";
        struct punctuation_capture expected[4];
        for (int level = 0; level < 4; ++level)
            expected[level] = speak_punctuation(text, languages[language], level, native, trace);
        for (int previous = 0; previous < 4; ++previous) {
            for (int level = 0; level < 4; ++level) {
                speak_punctuation(text, languages[language], previous, native, trace);
                struct punctuation_capture actual = speak_punctuation(text, languages[language], level, native, trace);
                require(strcmp(expected[level].phonemes, actual.phonemes) == 0,
                        "all 16 punctuation transitions restore the requested phonemes");
            }
        }
        if (!native) {
            struct capture rejected = {0};
            const int invalid[] = {-1, 4, INT_MIN, INT_MAX};
            for (size_t index = 0; index < sizeof(invalid) / sizeof(invalid[0]); ++index) {
                require(rb_espeak_synth(text, languages[language], "", 175, 50, 100, 50, 0, invalid[index],
                                       capture_pcm, &rejected) == RB_ESPEAK_INVALID_ARGUMENT,
                        "invalid punctuation rejected instead of clamped");
            }
            require(rejected.blocks == 0, "invalid punctuation emits no callbacks");
            for (int level = 0; level < 4; ++level) {
                require(espeak_SetPunctuationList(L"_") == EE_OK, "seed a foreign native list");
                require(espeak_SetParameter(espeakPUNCTUATION, espeakPUNCT_ALL, 0) == EE_OK,
                        "seed a foreign native mode");
                struct punctuation_capture actual = speak_punctuation(text, languages[language], level, 0, trace);
                require(strcmp(expected[level].phonemes, actual.phonemes) == 0,
                        "backend resets foreign native punctuation settings");
                struct capture cancelled = {0};
                cancelled.abort_after = 2;
                cancelled.check_reentry = 1;
                require(rb_espeak_synth(text, languages[language], "", 175, 50, 100, 50, 0, level,
                                       capture_pcm, &cancelled) == RB_ESPEAK_ABORTED,
                        "cancel punctuation synthesis");
                require(cancelled.blocks == 2, "punctuation abort stops callbacks");
                actual = speak_punctuation(text, languages[language], RB_ESPEAK_PUNCT_NONE, 0, trace);
                require(strcmp(expected[0].phonemes, actual.phonemes) == 0,
                        "punctuation and cancellation cannot leak into the next utterance");
            }
        }
    }
    require(fclose(trace) == 0, "close punctuation trace");
    fprintf(stderr, "PASS: %s punctuation, 28 symbols x 4 levels x 2 languages, all transitions%s\n",
            native ? "native" : "backend", native ? "" : ", invalid input, reentry, abort and recovery");
}

static int run_backend_tests(int argc, char **argv)
{
    setvbuf(stdout, NULL, _IOLBF, 0);
    require(argc >= 3, "usage: test_backend data-parent output-directory [reject|buffers|pcm|punctuation|punctuation-native|text-prefixes]");
    if (argc == 4 && strcmp(argv[3], "reject") == 0) {
        require(rb_espeak_init(argv[1]) < 0, "reject invalid data root");
        require(rb_espeak_voice_count(false) == 0, "no lists after failed init");
        puts("Invalid data root rejected");
        return 0;
    }
    if (argc == 4 && strcmp(argv[3], "buffers") == 0) {
        for (int iteration = 0; iteration < 12; ++iteration) {
            require(espeak_Initialize(AUDIO_OUTPUT_SYNCHRONOUS, 50, argv[1], 0) == 22050,
                    "50 ms initialization");
            espeak_SetSynthCallback(direct_pcm);
            require(espeak_SetVoiceByName("pl") == EE_OK, "direct Polish voice");
            require(espeak_Synth("test", 5, 0, POS_CHARACTER, 0, espeakCHARS_UTF8,
                                 NULL, NULL) == EE_OK, "50 ms synthesis");
            require(espeak_Terminate() == EE_OK, "terminate");
        }
        puts("50 ms buffer alignment and repeated lifecycle passed");
        return 0;
    }
    if (argc == 4 && strcmp(argv[3], "punctuation-native") == 0) {
        require(espeak_Initialize(AUDIO_OUTPUT_SYNCHRONOUS, 20, argv[1], 0) == 22050,
                "native punctuation initialization");
        espeak_SetSynthCallback(capture_native);
        test_punctuation(1, argv[2]);
        require(espeak_Terminate() == EE_OK, "native punctuation termination");
        return 0;
    }
    if (argc == 4 && strcmp(argv[3], "punctuation") == 0) {
        require(rb_espeak_init(argv[1]) == 22050, "backend punctuation initialization");
        test_punctuation(0, argv[2]);
        return 0;
    }
    if (argc == 4 && strcmp(argv[3], "text-prefixes") == 0) {
        require(rb_espeak_init(argv[1]) == 22050, "ordinary text initialization");
        test_text_prefixes(argv[2]);
        test_character_speech();
        require(espeak_Terminate() == EE_OK, "ordinary text termination");
        return 0;
    }
    record_pcm = argc == 4 && strcmp(argv[3], "pcm") == 0;
#ifdef _WIN32
    if (record_pcm)
        require(_setmode(_fileno(stdout), _O_BINARY) != -1, "binary PCM output");
#endif
    require(rb_espeak_voice_count(false) == 0, "no lists before init");
    require(rb_espeak_validate_voice("pl", "") == RB_ESPEAK_NOT_INITIALIZED,
            "validation before init");
    struct capture rejected = {0};
    require(rb_espeak_synth("test", "pl", "", 175, 50, 100, 50, 0, RB_ESPEAK_PUNCT_NONE,
                           capture_pcm, &rejected) == RB_ESPEAK_NOT_INITIALIZED,
            "synthesis before init");
    require(rb_espeak_init(NULL) == RB_ESPEAK_INVALID_ARGUMENT, "null root rejected");
    setlocale(LC_CTYPE, "C");
    require(rb_espeak_init(argv[1]) == 22050, "initialize exact supplied data");
    require(strcmp(setlocale(LC_CTYPE, NULL), "C") == 0, "global locale unchanged");
    require(rb_espeak_init(argv[1]) == 22050, "idempotent initialization");
    require(rb_espeak_init("/") < 0, "no root replacement");
    require(rb_espeak_voice_count(true) == 105, "104 variants plus default");
    require(rb_espeak_voice_id(true, 0)[0] == 0, "default variant has empty suffix");
    require(rb_espeak_voice_name(false, -1) == NULL, "negative choice index");
    require(rb_espeak_voice_id(true, INT_MAX) == NULL, "out-of-range choice index");
    require(rb_espeak_validate_voice("pl", "m3") == 0, "Polish variant found");
    require(rb_espeak_validate_voice("en", NULL) == 0, "English base voice found");
    require(rb_espeak_validate_voice("pl", "missing") == RB_ESPEAK_INVALID_VOICE,
            "unknown variant rejected");
    require(rb_espeak_validate_voice("../pl", "") == RB_ESPEAK_INVALID_VOICE,
            "voice traversal rejected");
    require(rb_espeak_synth("test", "missing", "", 175, 50, 100, 50, 0, RB_ESPEAK_PUNCT_NONE,
                           capture_pcm, &rejected) == RB_ESPEAK_INVALID_VOICE,
            "synthesis rejects an unknown language");
    require(rb_espeak_synth("test", "pl", "missing", 175, 50, 100, 50, 0, RB_ESPEAK_PUNCT_NONE,
                           capture_pcm, &rejected) == RB_ESPEAK_INVALID_VOICE,
            "synthesis rejects an unknown variant");
    require(rb_espeak_synth(NULL, "pl", "", 175, 50, 100, 50, 0, RB_ESPEAK_PUNCT_NONE,
                           capture_pcm, &rejected) == RB_ESPEAK_INVALID_ARGUMENT,
            "synthesis rejects null text");
    require(rb_espeak_synth("test", "pl", "", 175, 50, 100, 50, 0, RB_ESPEAK_PUNCT_NONE,
                           NULL, &rejected) == RB_ESPEAK_INVALID_ARGUMENT,
            "synthesis rejects a null callback");
    require(rejected.blocks == 0, "rejected requests emit no PCM");
    const char *stable_name = rb_espeak_voice_name(true, 1);
    char stable_copy[96];
    snprintf(stable_copy, sizeof(stable_copy), "%s", stable_name);
    struct capture ordinary = speak("Zażółć gęślą jaźń. Polska mowa.", "pl", "", 175, 50, 100, 50, 0);
    require(ordinary.nonzero, "Polish non-silent PCM");
    require(strcmp(setlocale(LC_CTYPE, NULL), "C") == 0, "synthesis restores locale");
    require(speak("English speech.", "en", "", 175, 50, 100, 50, 0).nonzero, "English PCM");
    struct capture cancelled = {0};
    cancelled.abort_after = 2;
    cancelled.check_reentry = 1;
    require(rb_espeak_synth("Długa wypowiedź do anulowania.", "pl", "m3", 175, 50, 100, 50, 0, RB_ESPEAK_PUNCT_NONE,
                           capture_pcm, &cancelled) == RB_ESPEAK_ABORTED, "callback cancellation");
    require(cancelled.blocks == 2, "no callbacks after abort");
    require(speak("Ponowna mowa.", "pl", "", 175, 50, 100, 50, 0).nonzero, "speech after abort");
    struct capture slow = speak("Pierwszy drugi trzeci.", "pl", "", 80, 50, 100, 50, 0);
    struct capture fast = speak("Pierwszy drugi trzeci.", "pl", "", 450, 50, 100, 50, 0);
    require(slow.samples > fast.samples, "rate affects duration");
    struct capture silence = speak("Cisza.", "pl", "", 175, 50, 0, 50, 0);
    require(!silence.nonzero, "zero volume produces silence");
    struct capture normal_gap = speak("Pierwszy drugi trzeci.", "pl", "", 175, 50, 100, 50, 0);
    struct capture wide_gap = speak("Pierwszy drugi trzeci.", "pl", "", 175, 50, 100, 50, 40);
    require(wide_gap.samples > normal_gap.samples, "word gap affects duration");
    struct capture low = speak("Pierwszy drugi trzeci.", "pl", "", 175, 0, 100, 50, 0);
    struct capture high = speak("Pierwszy drugi trzeci.", "pl", "", 175, 99, 100, 50, 0);
    require(low.checksum != high.checksum, "pitch affects PCM");
    struct capture narrow = speak("Pierwszy drugi trzeci.", "pl", "", 175, 50, 100, 0, 0);
    struct capture wide = speak("Pierwszy drugi trzeci.", "pl", "", 175, 50, 100, 99, 0);
    require(narrow.checksum != wide.checksum, "range affects PCM");
    fprintf(stderr, "rate samples: 80=%llu 450=%llu; wordgap samples: 0=%llu 40=%llu\n",
           (unsigned long long)slow.samples, (unsigned long long)fast.samples,
           (unsigned long long)normal_gap.samples, (unsigned long long)wide_gap.samples);
    fprintf(stderr, "pitch hashes: 0=%llu 99=%llu; range hashes: 0=%llu 99=%llu; volume0 nonzero=%d\n",
           (unsigned long long)low.checksum, (unsigned long long)high.checksum,
           (unsigned long long)narrow.checksum, (unsigned long long)wide.checksum, silence.nonzero);
    if (!record_pcm) {
        test_text_prefixes(argv[2]);
        test_word_positions();
        test_character_speech();
    }
    test_polish_trace(argv[2]);
    for (int index = 0; index < rb_espeak_voice_count(true); ++index) {
        const char *variant = rb_espeak_voice_id(true, index);
        struct capture result = speak("Polska mowa.", "pl", variant, 175, 50, 100, 50, 0);
        require(result.nonzero, variant);
        fprintf(stderr, "variant=%s samples=%llu nonzero=%d\n", variant,
               (unsigned long long)result.samples, result.nonzero);
    }
    for (int index = 0; index < rb_espeak_voice_count(false); ++index) {
        const char *language = rb_espeak_voice_id(false, index);
        require(speak("Test 123.", language, "", 175, 50, 100, 50, 0).nonzero, language);
        fprintf(stderr, "language=%s PCM passed\n", language);
    }
    require(stable_name == rb_espeak_voice_name(true, 1) && strcmp(stable_name, stable_copy) == 0,
            "choice storage immutable across voice changes");
    char long_text[1201];
    memset(long_text, 'a', sizeof(long_text) - 1);
    long_text[sizeof(long_text) - 1] = 0;
    speak(long_text, "pl", "", 175, 50, 100, 50, 0);
    speak("1234567890123456789012345678901 3,55555", "pl", "", 175, 50, 100, 50, 0);
    if (record_pcm)
        require(fflush(stdout) == 0, "flush PCM regression stream");
    fprintf(stderr, "PASS: %d languages, %d variants, PCM, parameters, abort, Polish ci, long input\n",
           rb_espeak_voice_count(false), rb_espeak_voice_count(true));
    return 0;
}

#ifdef _WIN32
int wmain(int argc, wchar_t **wide_arguments)
{
    char **arguments = calloc((size_t)argc + 1, sizeof(*arguments));
    require(arguments != NULL, "allocate argument array");
    for (int index = 0; index < argc; ++index) {
        int length = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS,
                                        wide_arguments[index], -1, NULL, 0, NULL, NULL);
        require(length > 0, "measure UTF-8 argument");
        arguments[index] = malloc((size_t)length);
        require(arguments[index] != NULL, "allocate UTF-8 argument");
        require(WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, wide_arguments[index], -1,
                                   arguments[index], length, NULL, NULL) > 0,
                "convert UTF-8 argument");
    }
    int result = run_backend_tests(argc, arguments);
    for (int index = 0; index < argc; ++index)
        free(arguments[index]);
    free(arguments);
    return result;
}
#else
int main(int argc, char **argv)
{
    return run_backend_tests(argc, argv);
}
#endif
