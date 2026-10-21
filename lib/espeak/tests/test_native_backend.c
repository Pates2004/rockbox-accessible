#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "rb_espeak.h"
#ifdef RB_ESPEAK_NATIVE_TEST_STATS
#include "native/native_runtime.h"
#endif

static uint64_t pcm_hash;
static size_t sample_count;
static size_t nonzero_count;
static unsigned int position_count;
static int last_position;
static int last_time;
static int abort_output;
static int check_reentry;
static int reentry_checked;

static void require(int condition, const char *message)
{
    if (!condition)
    {
        fprintf(stderr, "FAIL native backend: %s\n", message);
        exit(1);
    }
}

static int receive(const short *samples, int count, void *context)
{
    (void)context;
    if (check_reentry && !reentry_checked)
    {
        reentry_checked = 1;
        require(rb_espeak_synth("nested", "en", "", 175, 50, 100, 50, 0, 0,
                               receive, NULL) == RB_ESPEAK_BUSY, "reentry rejected");
    }
    for (int index = 0; index < count; ++index)
    {
        pcm_hash ^= (uint16_t)samples[index];
        pcm_hash *= UINT64_C(1099511628211);
        nonzero_count += samples[index] != 0;
    }
    sample_count += count;
    return abort_output;
}

static void position(int character, int milliseconds, void *context)
{
    (void)context;
    require(character >= last_position && milliseconds >= last_time, "ordered read positions");
    last_position = character;
    last_time = milliseconds;
    ++position_count;
}

static int synthesize(const char *text, const char *language, const char *variant,
                      int rate, int punctuation, int volume)
{
    pcm_hash = UINT64_C(1469598103934665603);
    sample_count = nonzero_count = position_count = 0;
    last_position = last_time = 0;
    return rb_espeak_synth_tracked(text, language, variant, rate, 50, volume,
                                   50, 0, punctuation, receive, position, NULL);
}

int main(int count, char **arguments)
{
    require(count == 2, "data parent argument");
    require(rb_espeak_init(arguments[1]) == 22050, "initialize native services");
    require(rb_espeak_init(arguments[1]) == 22050, "idempotent initialization");
    require(rb_espeak_voice_count(false) == 54, "all 54 languages");
    require(rb_espeak_voice_count(true) == 105, "all 105 variants");
    const char *text = "Zażółć gęślą jaźń. Pliki i foldery, 123! Hello world?";
    const int rates[] = {80, 175, 450, 451, 1350};
    const char *languages[] = {"pl", "en"};
    for (unsigned int language = 0; language < 2; ++language)
        for (unsigned int rate = 0; rate < sizeof(rates) / sizeof(rates[0]); ++rate)
            for (int punctuation = 0; punctuation < 4; ++punctuation)
            {
                require(synthesize(text, languages[language], "", rates[rate], punctuation, 100) == 0,
                        "rate/punctuation synthesis");
                require(sample_count && nonzero_count && position_count, "PCM and word events");
                printf("PCM %s %d %d %zu %" PRIu64 "\n", languages[language],
                       rates[rate], punctuation, sample_count, pcm_hash);
            }
    for (int index = 0; index < rb_espeak_voice_count(true); ++index)
    {
        const char *variant = rb_espeak_voice_id(true, index);
        require(synthesize("Polska mowa.", "pl", variant, 175, 0, 100) == 0 && nonzero_count,
                variant);
    }
    for (int index = 0; index < rb_espeak_voice_count(false); ++index)
    {
        const char *language = rb_espeak_voice_id(false, index);
        require(synthesize("Test 123.", language, "", 175, 0, 100) == 0 && nonzero_count,
                language);
    }
    require(synthesize("Cisza.", "pl", "", 175, 0, 0) == 0 && !nonzero_count,
            "zero volume produces silence");
    abort_output = 1;
    require(synthesize(text, "pl", "", 175, 0, 100) == RB_ESPEAK_ABORTED, "cancellation");
    abort_output = 0;
    check_reentry = 1;
    require(synthesize(text, "pl", "", 175, 0, 100) == 0 && nonzero_count,
            "recovery after cancellation");
    require(reentry_checked, "reentry callback occurred");
    check_reentry = 0;
    for (int index = 0; index < 100; ++index)
        require(synthesize("Test.", index % 2 ? "pl" : "en", "", 175, 0, 100) == 0,
                "repeated language changes");
#ifdef RB_ESPEAK_NATIVE_TEST_STATS
    printf("ENGINE_HEAP used=%zu peak=%zu failures=%zu\n", rb_espeak_heap_used(),
           rb_espeak_heap_peak(), rb_espeak_heap_failures());
    void *reservations[256];
    size_t reserved = 0;
    require(synthesize("Test.", "pl", "", 175, 0, 100) == 0, "prepare heap pressure");
    while (reserved < sizeof(reservations) / sizeof(reservations[0]))
    {
        void *memory = rb_espeak_malloc(8192);
        if (!memory)
            break;
        reservations[reserved++] = memory;
    }
    require(reserved > 0, "heap pressure established");
    size_t failures = rb_espeak_heap_failures();
    require(synthesize("Allocation failure.", "en", "", 175, 0, 100) < 0,
            "engine reports exhausted native heap");
    require(rb_espeak_heap_failures() > failures, "actual allocator rejection");
    while (reserved)
        rb_espeak_free(reservations[--reserved]);
    require(synthesize(text, "en", "", 175, 0, 100) == 0 && nonzero_count,
            "engine recovers after allocation failure");
    printf("HEAP capacity=%zu used=%zu peak=%zu failures=%zu\n", rb_espeak_heap_capacity(),
           rb_espeak_heap_used(), rb_espeak_heap_peak(), rb_espeak_heap_failures());
#endif
    puts("PASS: native services, 54 languages, 105 variants, rates, punctuation, events, cancellation and reentry");
    return 0;
}
