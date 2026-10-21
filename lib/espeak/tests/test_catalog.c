#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "engine/speak_lib.h"
#ifdef RB_ESPEAK_NATIVE_TEST_STATS
#include "native/native_runtime.h"
#endif

static size_t nonzero_samples;
static int abort_synthesis;

static void require(int condition, const char *message)
{
    if (!condition)
    {
        fprintf(stderr, "FAIL r34 catalog: %s\n", message);
        exit(1);
    }
}

static int receive(short *samples, int count, espeak_EVENT *events)
{
    (void)events;
    for (int index = 0; index < count; ++index)
        nonzero_samples += samples[index] != 0;
    return abort_synthesis;
}

static void speak(void)
{
    const char text[] = "Test speech after catalog selection.";
    nonzero_samples = 0;
    require(espeak_Synth(text, sizeof(text), 0, POS_CHARACTER, 0,
                         espeakCHARS_UTF8, NULL, NULL) == EE_OK, "synthesis");
    require(nonzero_samples > 0, "audible synthesis");
}

int main(int count, char **arguments)
{
    require(count == 2, "data parent argument");
    require(strstr(espeak_Info(NULL), "1.44.05-r34") != NULL, "r34 version");
#ifdef RB_ESPEAK_NATIVE_TEST_STATS
    size_t retained_heap = 0;
#endif
    for (int iteration = 0; iteration < 12; ++iteration)
    {
        require(espeak_Initialize(AUDIO_OUTPUT_SYNCHRONOUS, 50, arguments[1], 0)
                == 22050, "repeated initialization");
        espeak_SetSynthCallback(receive);
        for (int filtered = 0; filtered < 2; ++filtered)
        {
            espeak_VOICE selector = {0};
            selector.languages = "en";
            const espeak_VOICE **voices = espeak_ListVoices(filtered ? &selector : NULL);
            require(voices != NULL, "dynamic catalog allocation");
            int voice_count = 0;
            int found_last = 0;
            for (; voices[voice_count] != NULL; ++voice_count)
            {
                require(voice_count < 1000, "terminated catalog");
                found_last |= strcmp(voices[voice_count]->identifier, "r0199") == 0;
            }
            require(voice_count == 201 && found_last, "all 201 catalog entries");
        }
        espeak_VOICE selector = {0};
        selector.name = "Catalog 199";
        require(espeak_SetVoiceByProperties(&selector) == EE_OK, "last named voice");
        speak();
        selector.name = NULL;
        selector.languages = "en";
        selector.gender = 1;
        selector.variant = 199;
        require(espeak_SetVoiceByProperties(&selector) == EE_OK, "dynamic candidate selection");
        speak();
        abort_synthesis = 1;
        speak();
        require(espeak_Cancel() == EE_OK, "cancel before cleanup");
        abort_synthesis = 0;
        speak();
        require(espeak_Terminate() == EE_OK, "terminate");
        require(espeak_Terminate() == EE_OK, "idempotent terminate");
#ifdef RB_ESPEAK_NATIVE_TEST_STATS
        if (!iteration)
            retained_heap = rb_espeak_heap_used();
        require(rb_espeak_heap_used() == retained_heap, "no per-cycle heap growth");
#endif
    }
    puts("PASS: r34 dynamic catalog, 201 voices, selection, cancellation and 12 lifecycles");
    return 0;
}
