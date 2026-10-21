#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "rb_espeak.h"
#include "native/native_runtime.h"
#include "sonic/sonic.h"

static int fail_voice_copy;
static int reject_allocation;
static int rejected_allocations;
static int realloc_index;
static int rejected_realloc_index;
static int callback_count;
static int abort_after;
static int reentry_checked;
static const char *data_parent;

static void require(int condition, const char *message)
{
    if (!condition)
    {
        fprintf(stderr, "FAIL native ownership: %s\n", message);
        exit(1);
    }
}

void *__real_rb_espeak_malloc(size_t size);
void *__real_rb_espeak_realloc(void *memory, size_t size);
void *__wrap_rb_espeak_malloc(size_t size)
{
    if (reject_allocation)
    {
        reject_allocation = 0;
        ++rejected_allocations;
        return __real_rb_espeak_malloc(SIZE_MAX);
    }
    return __real_rb_espeak_malloc(size);
}

void *__wrap_rb_espeak_realloc(void *memory, size_t size)
{
    ++realloc_index;
    if (realloc_index == rejected_realloc_index)
        return __real_rb_espeak_malloc(SIZE_MAX);
    return __real_rb_espeak_realloc(memory, size);
}

void *select_translator(const char *language) __asm__("_Z16SelectTranslatorPKc");

static void test_translator_failures(void)
{
    const char *languages[] = {"en", "pl"};
    for (size_t index = 0; index < sizeof(languages) / sizeof(languages[0]); ++index)
    {
        size_t used = rb_espeak_heap_used();
        size_t failures = rb_espeak_heap_failures();
        reject_allocation = 1;
        require(select_translator(languages[index]) == NULL, "translator allocation failure returns NULL");
        require(!reject_allocation && rb_espeak_heap_failures() == failures + 1,
                "actual translator allocation rejected");
        require(rb_espeak_heap_used() == used, "translator failure retains no allocation");
    }
    puts("PASS: 2 translator allocation failures return NULL without heap growth");
}

static void test_sonic_failures(void)
{
    short samples[4000] = {0};
    for (int failure = 0; failure <= 2; ++failure)
    {
        size_t used = rb_espeak_heap_used();
        size_t failures = rb_espeak_heap_failures();
        sonicStream stream = sonicCreateStream(22050, 1);
        require(stream != NULL, "create Sonic allocation fixture");
        realloc_index = 0;
        rejected_realloc_index = failure;
        int result = sonicWriteShortToStream(stream, samples, 4000);
        require(failure ? !result : result, "Sonic input/output growth failure reported");
        require(!failure || realloc_index == failure, "requested Sonic realloc failure reached");
        rejected_realloc_index = 0;
        sonicDestroyStream(stream);
        require(rb_espeak_heap_used() == used, "failed Sonic growth preserves ownership for cleanup");
        require(rb_espeak_heap_failures() == failures + (failure != 0), "exact Sonic failure count");
        stream = sonicCreateStream(22050, 1);
        require(stream && sonicWriteShortToStream(stream, samples, 4000), "Sonic allocation recovery");
        sonicDestroyStream(stream);
        require(rb_espeak_heap_used() == used, "Sonic recovery releases every buffer");
    }
    puts("PASS: Sonic input/output realloc failure cleanup and recovery, no retained bytes");
}

void __real__Z13DoVoiceChangeP7voice_t(void *voice);
void __wrap__Z13DoVoiceChangeP7voice_t(void *voice)
{
    if (fail_voice_copy)
    {
        fail_voice_copy = 0;
        reject_allocation = 1;
    }
    __real__Z13DoVoiceChangeP7voice_t(voice);
    require(!reject_allocation, "voice copy reached the real allocator");
}

static int receive(const short *samples, int count, void *context)
{
    (void)context;
    require(samples && count > 0, "valid PCM callback");
    ++callback_count;
    if (!reentry_checked)
    {
        reentry_checked = 1;
        require(rb_espeak_init(data_parent) == RB_ESPEAK_BUSY, "initializer reentry rejected");
        require(rb_espeak_synth("Nested speech.", "en", "", 175, 50, 100, 50, 0, 0,
                               receive, NULL) == RB_ESPEAK_BUSY, "synthesis reentry rejected");
        require(rb_espeak_validate_voice("en", "") == RB_ESPEAK_OK,
                "immutable catalog remains readable during synthesis");
    }
    return abort_after && callback_count >= abort_after;
}

static int speak(const char *language, const char *variant, int rate)
{
    callback_count = 0;
    reentry_checked = 0;
    return rb_espeak_synth("First second third fourth. Another phrase.", language, variant,
                           rate, 50, 100, 50, 0, 0, receive, NULL);
}

int main(int count, char **arguments)
{
    require(count == 2 || count == 3, "data parent and optional isolated regression");
    data_parent = arguments[1];
    if (count == 3)
    {
        require(!strcmp(arguments[2], "translator") || !strcmp(arguments[2], "sonic"),
                "recognized isolated regression");
        if (!strcmp(arguments[2], "translator"))
            test_translator_failures();
        else
            test_sonic_failures();
        return 0;
    }
    require(rb_espeak_init(data_parent) == 22050, "initialize");
    test_translator_failures();
    test_sonic_failures();
    require(speak("pl", "", 175) == RB_ESPEAK_OK, "warm up");
    for (int rate_index = 0; rate_index < 2; ++rate_index)
    {
        int rate = rate_index ? 1350 : 175;
        size_t failures = rb_espeak_heap_failures();
        int rejected = rejected_allocations;
        fail_voice_copy = 1;
        require(speak("pl", "m3", rate) == RB_ESPEAK_ERROR,
                "ignored voice-copy allocation failure must not report success");
        require(rejected_allocations == rejected + 1 && rb_espeak_heap_failures() == failures + 1,
                "actual bounded allocator failure injected once");
        require(speak("en", "f3", rate) == RB_ESPEAK_OK && callback_count,
                "successful recovery despite historical allocator failures");
    }
    size_t retained_heap = 0;
    for (int cycle = 0; cycle < 24; ++cycle)
    {
        for (int selection = 0; selection < 4; ++selection)
        {
            const char *language = selection % 2 ? "en" : "pl";
            const char *variant = selection < 2 ? "m3" : "f3";
            int rate = selection % 2 ? 1350 : 175;
            abort_after = 1 + cycle % 4;
            require(speak(language, variant, rate) == RB_ESPEAK_ABORTED,
                    "ordinary and Sonic cancellation");
            require(callback_count == abort_after, "no PCM after cancellation");
            abort_after = 0;
            require(speak(language, variant, rate) == RB_ESPEAK_OK && callback_count,
                    "language and variant recovery after cancellation");
        }
        require(speak("pl", "", 175) == RB_ESPEAK_OK, "normalize retained voice");
        size_t used = rb_espeak_heap_used();
        if (cycle < 2)
            retained_heap = used;
        else
            require(used == retained_heap, "no steady-state heap growth across lifecycle cycles");
    }
    require(rb_espeak_heap_failures() == 6, "no unexpected allocation failures");
    printf("PASS: native ownership, 6 allocation-failure regressions, 96 cancellations, "
           "96 recoveries, 24 lifecycle cycles (22 steady-state checks); used=%zu\n", retained_heap);
    return 0;
}
