#include "rb_espeak.h"
#include "engine/speak_lib.h"
#include "sonic/sonic.h"

#include <limits.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <windows.h>
#include <fcntl.h>
#include <io.h>
#endif

enum fault { NO_FAULT, CREATE_FAULT, WRITE_FAULT, READ_FAULT, FLUSH_FAULT, SYNTH_FAULT,
             RATE_ZERO_FAULT, RATE_NEGATIVE_FAULT };
struct mark { int character; int milliseconds; };
struct capture {
    uint64_t samples;
    uint64_t native_samples;
    uint64_t checksum;
    int nonzero;
    int blocks;
    int native_blocks;
    int partial_blocks;
    int normal_partial_blocks;
    int abort_after;
    int reenter;
    int tracked;
    int characters;
    int words;
    int native_words;
    int checked_words;
    int adjusted_rate;
    int requested_rate;
    int stream_created;
    int abort_on_flush;
    struct mark marks[2048];
    struct mark native_marks[2048];
};

static struct capture *current;
static enum fault fault;
static int live_streams;
static int native_rate;
static int flushes;
static int flushing;
static int require_full_chunks = 1;
static int record_chunk_pcm;
static t_espeak_callback *bridge_callback;
static const short *native_block;
static int native_count;
static int collect_pitch;
static short pitch_input[220500];
static short pitch_output[220500];
static int pitch_input_count;
static int pitch_output_count;

static void require(int condition, const char *message)
{
    if (!condition) {
        fprintf(stderr, "FAIL: %s (rate=%d, adjusted=%d, output=%llu, native=%llu)\n",
                message, current ? current->requested_rate : 0,
                current ? current->adjusted_rate : 0,
                (unsigned long long)(current ? current->samples : 0),
                (unsigned long long)(current ? current->native_samples : 0));
        exit(1);
    }
}

int __real_espeak_SetSonicRate(int rate);
int __wrap_espeak_SetSonicRate(int rate)
{
    require(rate == 0 || (rate > 450 && rate <= 1350), "bounded native Sonic rate");
    native_rate = rate;
    int adjusted = __real_espeak_SetSonicRate(rate);
    if (rate && fault == RATE_ZERO_FAULT)
        adjusted = 0;
    if (rate && fault == RATE_NEGATIVE_FAULT)
        adjusted = -1;
    if (current && rate) {
        current->requested_rate = rate;
        current->adjusted_rate = adjusted;
    }
    return adjusted;
}

static int inspect_native(short *samples, int count, espeak_EVENT *events)
{
    native_block = samples;
    native_count = count;
    if (current) {
        if (samples && count > 0) {
            current->native_samples += count;
            ++current->native_blocks;
            if (collect_pitch && pitch_input_count + count <= 220500) {
                memcpy(pitch_input + pitch_input_count, samples, count * sizeof(short));
                pitch_input_count += count;
            }
        }
        if (current->tracked && events)
            for (espeak_EVENT *event = events; event->type; ++event)
                if (event->type == espeakEVENT_WORD && event->length > 0 &&
                    event->text_position > 0 && event->text_position <= current->characters &&
                    (!current->native_words || event->text_position >
                     current->native_marks[current->native_words - 1].character)) {
                    require(current->native_words < 2048, "native event fixture capacity");
                    current->native_marks[current->native_words++] =
                        (struct mark){event->text_position, event->audio_position};
                }
    }
    return bridge_callback(samples, count, events);
}

void __real_espeak_SetSynthCallback(t_espeak_callback *callback);
void __wrap_espeak_SetSynthCallback(t_espeak_callback *callback)
{
    bridge_callback = callback;
    __real_espeak_SetSynthCallback(inspect_native);
}

espeak_ERROR __real_espeak_Synth(const void *, size_t, unsigned int,
    espeak_POSITION_TYPE, unsigned int, unsigned int, unsigned int *, void *);
espeak_ERROR __wrap_espeak_Synth(const void *text, size_t size, unsigned int position,
    espeak_POSITION_TYPE type, unsigned int end, unsigned int flags,
    unsigned int *identifier, void *user)
{
    if (fault == SYNTH_FAULT)
        return EE_INTERNAL_ERROR;
    return __real_espeak_Synth(text, size, position, type, end, flags, identifier, user);
}

#if RB_ESPEAK_HAVE_SONIC
sonicStream __real_sonicCreateStream(int rate, int channels);
sonicStream __wrap_sonicCreateStream(int rate, int channels)
{
    flushing = 0;
    require(rate == 22050 && channels == 1, "Sonic mono22050");
    if (fault == CREATE_FAULT)
        return NULL;
    sonicStream stream = __real_sonicCreateStream(rate, channels);
    if (stream) {
        ++live_streams;
        if (current)
            current->stream_created = 1;
    }
    return stream;
}

void __real_sonicDestroyStream(sonicStream stream);
void __wrap_sonicDestroyStream(sonicStream stream)
{
    --live_streams;
    __real_sonicDestroyStream(stream);
}

int __real_sonicWriteShortToStream(sonicStream stream, const short *samples, int count);
int __wrap_sonicWriteShortToStream(sonicStream stream, const short *samples, int count)
{
    return fault == WRITE_FAULT ? 0 : __real_sonicWriteShortToStream(stream, samples, count);
}

int __real_sonicReadShortFromStream(sonicStream stream, short *samples, int count);
int __wrap_sonicReadShortFromStream(sonicStream stream, short *samples, int count)
{
    return fault == READ_FAULT ? 0 : __real_sonicReadShortFromStream(stream, samples, count);
}

int __real_sonicFlushStream(sonicStream stream);
int __wrap_sonicFlushStream(sonicStream stream)
{
    ++flushes;
    flushing = 1;
    return fault == FLUSH_FAULT ? 0 : __real_sonicFlushStream(stream);
}
#endif

static int capture_pcm(const short *samples, int count, void *context)
{
    struct capture *capture = context;
    require(samples && count > 0 && count <= 441, "bounded PCM block");
    if (record_chunk_pcm)
        require(fwrite(samples, sizeof(short), count, stdout) == (size_t)count,
                "write chunk PCM fingerprint stream");
    require(!capture->abort_after || capture->blocks < capture->abort_after,
            "no callback after abort");
    if (capture->stream_created && require_full_chunks) {
        require(!capture->partial_blocks, "no output callback after final partial block");
        require(count == 441 || flushing, "normal Sonic callbacks contain441 output samples");
    }
    if (count < 441) {
        ++capture->partial_blocks;
        if (!flushing)
            ++capture->normal_partial_blocks;
    }
    capture->samples += count;
    ++capture->blocks;
    for (int index = 0; index < count; ++index) {
        capture->nonzero |= samples[index] != 0;
        capture->checksum = capture->checksum * 33 + (uint16_t)samples[index];
    }
    if (!capture->stream_created)
        require(count == native_count && memcmp(samples, native_block, count * sizeof(short)) == 0,
                "ordinary PCM bypass is byte-identical for every block");
    if (collect_pitch && pitch_output_count + count <= 220500) {
        memcpy(pitch_output + pitch_output_count, samples, count * sizeof(short));
        pitch_output_count += count;
    }
    while (capture->checked_words < capture->words) {
        int time = capture->marks[capture->checked_words++].milliseconds;
        require((uint64_t)time * 22050 <= capture->samples * 1000,
                "marks never precede availability of their output clock");
    }
    if (capture->reenter) {
        capture->reenter = 0;
        int saved_rate = native_rate;
        require(rb_espeak_synth("test", "pl", "", INT_MAX, 50, 100, 50, 0, 0,
                capture_pcm, context) == RB_ESPEAK_BUSY, "PCM reentry guard");
        require(saved_rate == native_rate, "reentry does not reset active Sonic state");
    }
    return (capture->abort_after && capture->blocks >= capture->abort_after) ||
           (capture->abort_on_flush && flushing);
}

static void capture_position(int character, int milliseconds, void *context)
{
    struct capture *capture = context;
    require(character > 0 && character <= capture->characters && milliseconds >= 0,
            "Unicode position and time bounds");
    require(capture->words < 2048, "word fixture capacity");
    if (capture->words) {
        require(character > capture->marks[capture->words - 1].character, "ordered positions");
        require(milliseconds >= capture->marks[capture->words - 1].milliseconds,
                "ordered output clock");
    }
    require(rb_espeak_synth("test", "pl", "", 175, 50, 100, 50, 0, 0,
            capture_pcm, context) == RB_ESPEAK_BUSY, "position reentry guard");
    capture->marks[capture->words++] = (struct mark){character, milliseconds};
}

static int speak(struct capture *capture, const char *text, const char *language,
                 const char *variant, int rate, int volume, int punctuation)
{
    current = capture;
    flushing = 0;
    for (const unsigned char *byte = (const unsigned char *)text; *byte; ++byte)
        if ((*byte & 0xc0) != 0x80)
            ++capture->characters;
    int result = rb_espeak_synth_tracked(text, language, variant, rate, 50, volume, 50, 0,
        punctuation, capture_pcm, capture->tracked ? capture_position : NULL, capture);
    require(native_rate == 0 && live_streams == 0, "native rate and stream cleanup");
    if (result == RB_ESPEAK_OK && capture->stream_created && require_full_chunks)
        require((uint64_t)capture->blocks == (capture->samples + 440) / 441,
                "bounded callback count matches actual compressed duration");
    if (result == RB_ESPEAK_OK && capture->tracked && capture->stream_created) {
        require(capture->words == capture->native_words && capture->words > 0,
                "all real word events retained");
        for (int index = 0; index < capture->words; ++index) {
            struct mark actual = capture->marks[index];
            struct mark original = capture->native_marks[index];
            int expected = (int)(((int64_t)original.milliseconds * 175 +
                capture->adjusted_rate - 1) / capture->adjusted_rate);
            int duration = (int)(capture->samples * 1000 / 22050);
            if (expected > duration)
                expected = duration;
            require(actual.character == original.character && actual.milliseconds == expected,
                    "real native word mapped by adjusted speed, never native synthesis time");
            require(actual.milliseconds <= duration, "word within final compressed PCM");
        }
    }
    return result;
}

static double fundamental(const short *samples, int count)
{
    double best_score = 0;
    double peak_score = 0;
    int best_period = 0;
    for (int start = 128; start + 1024 < count; start += 128) {
        double scores[301] = {0};
        for (int period = 65; period <= 300; ++period) {
            double correlation = 0, energy_left = 0, energy_right = 0;
            for (int index = 0; index < 512; ++index) {
                double left = samples[start + index];
                double right = samples[start + index + period];
                correlation += left * right;
                energy_left += left * left;
                energy_right += right * right;
            }
            if (energy_left > 1e8 && energy_right > 1e8)
                scores[period] = correlation / sqrt(energy_left * energy_right);
            if (scores[period] > peak_score)
                peak_score = scores[period];
        }
        for (int period = 66; period < 300; ++period)
            if (scores[period] > 0.8 && scores[period] > scores[period - 1] &&
                scores[period] >= scores[period + 1]) {
                if (scores[period] > best_score) {
                    best_score = scores[period];
                    best_period = period;
                }
                break;
            }
    }
    fprintf(stderr, "pitch estimate samples=%d periodicity=%.3f period=%d\n", count,
            peak_score, best_period);
    require(best_period != 0, "voiced PCM pitch estimate");
    return 22050.0 / best_period;
}

static void test_rates(void)
{
    for (int rate = 80; rate <= 450; ++rate) {
        struct capture capture = {0};
        require(speak(&capture, "One two.", "en", "", rate, 100, 0) == RB_ESPEAK_OK &&
                capture.nonzero && !capture.stream_created && !capture.requested_rate,
                "every ordinary rate bypasses Sonic with byte-identical native PCM");
    }
    const char *text = "Pierwszy drugi trzeci czwarty piaty szosty siodmy osmy dziewiaty dziesiaty.";
    const int rates[] = {INT_MIN, -1, 0, 79, 80, 175, 449, 450, 451, 500, 600,
                         750, 900, 1050, 1200, 1349, 1350, 1351, INT_MAX};
    uint64_t maximum_samples = 0, minimum_samples = 0, native_fast = 0;
    for (size_t index = 0; index < sizeof(rates) / sizeof(rates[0]); ++index) {
        struct capture capture = {0};
        capture.tracked = rates[index] > 450;
        require(speak(&capture, text, "pl", "", rates[index], 100, 0) == RB_ESPEAK_OK,
                "representative full-range synthesis");
        require(capture.nonzero, "nonzero real PCM at every tested rate");
        if (rates[index] <= 80) {
            if (minimum_samples)
                require(fabs((double)capture.samples - minimum_samples) <= 441,
                        "80 lower clamp including zero/INT_MIN");
            minimum_samples = capture.samples;
        }
        if (rates[index] == 450)
            native_fast = capture.samples;
        if (rates[index] >= 1350) {
            if (maximum_samples)
                require(fabs((double)capture.samples - maximum_samples) <= 441,
                        "1350 upper clamp including INT_MAX");
            maximum_samples = capture.samples;
        }
#if RB_ESPEAK_HAVE_SONIC
        require(capture.stream_created == (rates[index] > 450), "450/451 stream boundary");
        if (capture.stream_created) {
            double expected = (double)capture.native_samples * 175 / capture.adjusted_rate;
            require(fabs(capture.samples - expected) < 441,
                    "actual compression duration follows prepared stream speed");
        }
#else
        require(!capture.stream_created && !capture.requested_rate, "disabled Sonic never prepared");
        if (rates[index] > 450)
            require(fabs((double)capture.samples - native_fast) <= 441,
                    "optional disabled build caps at450");
#endif
        fprintf(stderr, "rate=%d samples=%llu native=%llu words=%d adjusted=%d\n", rates[index],
                (unsigned long long)capture.samples, (unsigned long long)capture.native_samples,
                capture.words, capture.adjusted_rate);
    }
#if RB_ESPEAK_HAVE_SONIC
    require(maximum_samples < native_fast * 3 / 4, "1350 produces genuinely shorter PCM than450");
#endif
}

static void test_voices(void)
{
    for (int variants = 0; variants <= 1; ++variants)
        for (int index = 0; index < rb_espeak_voice_count(variants != 0); ++index) {
            const char *identifier = rb_espeak_voice_id(variants != 0, index);
            struct capture capture = {0};
            require(speak(&capture, "Testing sound one two three. Ala ma kota.",
                    variants ? "pl" : identifier, variants ? identifier : "", 1350, 100, 0)
                    == RB_ESPEAK_OK && capture.nonzero, "all language/variant high-rate actual PCM");
            fprintf(stderr, "voice=%s variant=%d output=%llu adjusted=%d\n", identifier,
                    variants, (unsigned long long)capture.samples, capture.adjusted_rate);
        }
    const int rates[] = {450, 451, 475, 500, 525, 550, 563, 564, 750, 1350};
    uint64_t ordinary_samples = 0;
    uint64_t previous_samples = 0;
    for (size_t index = 0; index < sizeof(rates) / sizeof(rates[0]); ++index) {
        struct capture capture = {0};
        capture.tracked = rates[index] > 450;
        require(speak(&capture, "coi ro do mi tavla do", "jbo", "", rates[index], 100, 0)
                == RB_ESPEAK_OK && capture.nonzero, "language speed modifier PCM");
#if RB_ESPEAK_HAVE_SONIC
        if (rates[index] > 450) {
            require(capture.adjusted_rate == rates[index] * 80 / 100, "jbo native speed80 adjustment");
            require(capture.stream_created, "prepared articulation always gets Sonic compression");
            require(capture.samples < ordinary_samples * 5 / 4,
                    "speed80 boundary never falls back to uncompressed slow preparation");
            double expected = (double)capture.native_samples * 175 / capture.adjusted_rate;
            require(fabs(capture.samples - expected) < 441,
                    "speed80 actual compression even when adjusted rate is below450");
            if (previous_samples)
                require(capture.samples < previous_samples,
                        "increasing451..563 and above shortens actual speed80 audio");
            previous_samples = capture.samples;
        }
#endif
        if (rates[index] == 450)
            ordinary_samples = capture.samples;
        fprintf(stderr, "jbo rate=%d adjusted=%d samples=%llu\n", rates[index],
                capture.adjusted_rate, (unsigned long long)capture.samples);
    }
    (void)ordinary_samples;
    (void)previous_samples;
}

static void test_recovery(void)
{
    for (int block = 1; block <= 12; ++block) {
        struct capture capture = {0};
        capture.abort_after = block;
        capture.reenter = 1;
        capture.tracked = 1;
        int initial_flushes = flushes;
        require(speak(&capture, "Pierwszy drugi trzeci czwarty piaty szosty siodmy osmy.",
                "pl", "", 900, 100, 0) == RB_ESPEAK_ABORTED, "abort compressed stream");
        require(capture.blocks == block && flushes == initial_flushes, "abort discards buffered tail");
        struct capture recovery = {0};
        require(speak(&recovery, "Recovered speech.", "en", "", 175, 100, 0) == RB_ESPEAK_OK &&
                recovery.nonzero && !recovery.stream_created, "ordinary recovery after high-rate abort");
    }
#if RB_ESPEAK_HAVE_SONIC
    struct capture tail = {0};
    tail.abort_on_flush = 1;
    require(speak(&tail, "a", "pl", "", 1350, 100, 0) == RB_ESPEAK_ABORTED && tail.blocks,
            "abort during final flushed PCM also cleans up");
    for (fault = CREATE_FAULT; fault <= RATE_NEGATIVE_FAULT; fault++) {
        struct capture capture = {0};
        require(speak(&capture, "Speech for failure injection.", "en", "", 900, 100, 0)
                == RB_ESPEAK_ERROR, "Sonic/native error is reported");
        enum fault saved = fault;
        fault = NO_FAULT;
        struct capture recovery = {0};
        require(speak(&recovery, "Recovery after an error.", "en", "", 1350, 100, 0)
                == RB_ESPEAK_OK && recovery.nonzero, "high-rate recovery after error");
        fault = saved;
    }
    fault = NO_FAULT;
#endif
    struct capture invalid = {0};
    require(speak(&invalid, "invalid", "missing", "", INT_MAX, 100, 0)
            == RB_ESPEAK_INVALID_VOICE && !invalid.blocks, "invalid voice no output");
    memset(&invalid, 0, sizeof(invalid));
    require(speak(&invalid, "invalid", "pl", "", INT_MAX, 100, INT_MIN)
            == RB_ESPEAK_INVALID_ARGUMENT && !invalid.blocks, "invalid punctuation no output");
}

static void test_text(void)
{
    const char *text = "\xc4\x85 b c. First second third. Fourth fifth sixth.";
    for (int punctuation = 0; punctuation <= 3; ++punctuation) {
        struct capture capture = {0};
        capture.tracked = 1;
        require(speak(&capture, text, "pl", "m3", 1350, 100, punctuation) == RB_ESPEAK_OK,
                "tracked Unicode with native punctuation");
        require(capture.words >= 9 && capture.marks[0].character == 1 &&
                capture.marks[1].character == 3 && capture.marks[2].character == 5,
                "original one-based Unicode word indices");
    }
    char long_text[9000] = {0};
    for (int index = 0; index < 1000; ++index)
        strcat(long_text, "one two ");
    struct capture long_capture = {0};
    long_capture.tracked = 1;
    require(speak(&long_capture, long_text, "en", "", 1350, 100, 0) == RB_ESPEAK_OK &&
            long_capture.words == 2000, "bounded streaming of2000 real word events");
    struct capture silent = {0};
    require(speak(&silent, text, "pl", "", 1350, 0, 0) == RB_ESPEAK_OK &&
            silent.samples > 0 && !silent.nonzero, "volume0 stays silent through Sonic");
    const unsigned int characters[] = {'a', 0x105, '.', ' ', '\n', 0x1f600};
    for (size_t index = 0; index < sizeof(characters) / sizeof(characters[0]); ++index) {
        struct capture capture = {0};
        current = &capture;
        require(rb_espeak_synth_character(characters[index], "pl", "", 1350, 50, 100,
                50, 0, capture_pcm, &capture) == RB_ESPEAK_OK && capture.nonzero,
                "native character or numeric fallback remains audible");
        require(!native_rate && !live_streams, "character cleanup");
    }
    struct capture silent_character = {0};
    current = &silent_character;
    require(rb_espeak_synth_character(0x1f600, "pl", "", 1350, 50, 0, 50, 0,
            capture_pcm, &silent_character) == RB_ESPEAK_OK && !silent_character.nonzero,
            "volume0 character does not produce audible numeric fallback");
}

static int run_tests(const char *data)
{
    require(rb_espeak_init(data) == 22050, "initialization");
#if RB_ESPEAK_HAVE_SONIC
    collect_pitch = 1;
    struct capture vowel = {0};
    require(speak(&vowel, "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "pl", "", 900, 100, 0)
            == RB_ESPEAK_OK && vowel.nonzero, "real vowel through Sonic");
    double input_pitch = fundamental(pitch_input, pitch_input_count);
    double output_pitch = fundamental(pitch_output, pitch_output_count);
    fprintf(stderr, "voiced pitch input=%.2fHz output=%.2fHz\n", input_pitch, output_pitch);
    require(fabs(input_pitch - output_pitch) / input_pitch < 0.15,
            "time compression retains measured voice pitch within15percent");
#else
    (void)fundamental;
#endif
    collect_pitch = 0;
    test_rates();
    test_voices();
    test_recovery();
    test_text();
    current = NULL;
    fprintf(stderr, "PASS: real PCM/range/clamps/events/voices/cleanup/recovery/pitch (Sonic=%d)\n",
            RB_ESPEAK_HAVE_SONIC);
    return 0;
}

static int run_command(int argc, char **arguments)
{
    if (argc == 2)
        return run_tests(arguments[1]);
    require(argc == 4 && (!strcmp(arguments[2], "--chunk-probe") ||
            !strcmp(arguments[2], "--chunk-check")), "data parent and optional chunk mode/rate");
    require_full_chunks = strcmp(arguments[2], "--chunk-probe") != 0;
    record_chunk_pcm = 1;
#ifdef _WIN32
    require(_setmode(_fileno(stdout), _O_BINARY) != -1, "binary PCM stdout");
#endif
    char *end;
    long rate = strtol(arguments[3], &end, 10);
    require(!*end && rate >= 451 && rate <= 1350, "chunk fixture high rate");
    require(rb_espeak_init(arguments[1]) == 22050, "chunk fixture initialization");
    char text[1024] = {0};
    for (int index = 0; index < 9; ++index)
        strcat(text, "Szybkie czytanie ma skracac rzeczywisty czas odtwarzania calego tekstu. ");
    struct capture capture = {0};
    capture.tracked = 1;
    require(speak(&capture, text, "pl", "", (int)rate, 100, 0) == RB_ESPEAK_OK &&
            capture.nonzero, "real chunk-throughput fixture");
    fprintf(stderr, "{\"rate\":%ld,\"samples\":%llu,\"native_samples\":%llu,\"blocks\":%d,"
           "\"native_blocks\":%d,\"partial_blocks\":%d,\"normal_partial_blocks\":%d,"
           "\"checksum\":\"%016llx\",\"words\":%d}\n", rate,
           (unsigned long long)capture.samples, (unsigned long long)capture.native_samples,
           capture.blocks, capture.native_blocks, capture.partial_blocks,
           capture.normal_partial_blocks, (unsigned long long)capture.checksum, capture.words);
    current = NULL;
    return 0;
}

#ifdef _WIN32
int wmain(int argc, wchar_t **wide_arguments)
{
    require(argc == 2 || argc == 4, "data parent and optional chunk mode/rate");
    char converted[4][1024];
    char *arguments[4];
    for (int index = 0; index < argc; ++index) {
        require(WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, wide_arguments[index], -1,
                converted[index], sizeof(converted[index]), NULL, NULL) > 0,
                "UTF8 argument conversion");
        arguments[index] = converted[index];
    }
    return run_command(argc, arguments);
}
#else
int main(int argc, char **arguments)
{
    return run_command(argc, arguments);
}
#endif
