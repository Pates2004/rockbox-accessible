#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(condition) do { if (!(condition)) { fprintf(stderr, "line %d: %s\n", __LINE__, #condition); exit(1); } } while (0)
#define MIN(first, second) ((first) < (second) ? (first) : (second))
#define SDL_MAJOR_VERSION 2
#define MIX_FRAME_SAMPLES 1024
#define SDL_INIT_AUDIO 1
#define SDL_AUDIO_ALLOW_SAMPLES_CHANGE 1
#define AUDIO_U8 8
#define AUDIO_S8 32776
#define AUDIO_U16LSB 16
#define AUDIO_S16LSB 32784
#define AUDIO_U16MSB 4112
#define AUDIO_S16MSB 36880
#define AUDIO_S32MSB 36896
#define AUDIO_S32LSB 32800
#define AUDIO_F32MSB 37152
#define AUDIO_F32LSB 33056
#define AUDIO_S16SYS AUDIO_S16LSB

typedef uint8_t Uint8;
typedef uint16_t Uint16;
typedef uint32_t Uint32;
typedef struct { int freq; unsigned format, channels, samples; Uint8 silence;
    void (*callback)(void *, Uint8 *, int); void *userdata; } SDL_AudioSpec;
typedef struct { int needed, len, len_mult, len_cvt; double len_ratio; Uint8 *buf; } SDL_AudioCVT;
static SDL_AudioSpec obtained;
static SDL_AudioCVT cvt;
static unsigned long pcm_sampr;
static const void *pcm_data;
static size_t pcm_sample_bytes, pcm_channel_bytes;
static int pcm_devid, cvt_status;
static void *audio_lock;
static const char *audiodev;
static const unsigned hw_freq_sampr[] = {44100};
static FILE mock_stream;
static unsigned opens, writes, closes, errors, pauses;
static bool open_failure, short_write, stream_failure, close_failure;
static char last_mode[8], logs[16384];
static Uint8 output[256], input[256], trace[256];
static size_t trace_bytes;

static inline void trace_log(const char *format, ...)
{
    size_t used = strlen(logs);
    va_list arguments;
    va_start(arguments, format);
    vsnprintf(logs + used, sizeof(logs) - used, format, arguments);
    va_end(arguments);
}

static inline FILE *mock_fopen(const char *path, const char *mode)
{
    CHECK(!strcmp(path, "audiodebug.raw"));
    ++opens;
    snprintf(last_mode, sizeof(last_mode), "%s", mode);
    return open_failure ? NULL : &mock_stream;
}

static inline size_t mock_fwrite(const void *data, size_t size, size_t count, FILE *stream)
{
    CHECK(stream == &mock_stream && size == 1 && count <= sizeof(trace));
    ++writes;
    trace_bytes = short_write ? count - 1 : count;
    memcpy(trace, data, trace_bytes);
    return trace_bytes;
}

static inline int mock_fclose(FILE *stream)
{
    CHECK(stream == &mock_stream);
    ++closes;
    return close_failure ? EOF : 0;
}

static inline int mock_ferror(FILE *stream)
{
    CHECK(stream == &mock_stream);
    ++errors;
    return stream_failure;
}

static inline void SDL_PauseAudioDevice(int device, int paused)
{
    (void)device;
    CHECK(paused == 1);
    ++pauses;
}
static inline int SDL_InitSubSystem(int flags) { CHECK(flags == SDL_INIT_AUDIO); return 0; }
static inline int SDL_GetNumAudioDrivers(void) { return 1; }
static inline const char *SDL_GetAudioDriver(int index) { CHECK(index == 0); return "disk"; }
static inline const char *SDL_GetCurrentAudioDriver(void) { return "disk"; }
static inline int SDL_GetNumAudioDevices(int capture) { CHECK(capture == 0); return 1; }
static inline const char *SDL_GetAudioDeviceName(int index, int capture) { CHECK(!index && !capture); return "disk"; }
static inline void *SDL_CreateMutex(void) { return &mock_stream; }
static inline void SDL_CloseAudioDevice(int device) { (void)device; }
static inline int SDL_OpenAudioDevice(const char *name, int capture, const SDL_AudioSpec *wanted,
                                      SDL_AudioSpec *actual, int flags)
{
    (void)name;
    CHECK(!capture && flags == SDL_AUDIO_ALLOW_SAMPLES_CHANGE);
    *actual = *wanted;
    return 1;
}
static inline const char *SDL_GetError(void) { return "mock error"; }
static inline int SDL_BuildAudioCVT(SDL_AudioCVT *conversion, int format, int channels, int rate,
                                    int output_format, int output_channels, int output_rate)
{
    CHECK(format == AUDIO_S16SYS && channels == 2 && rate == 44100);
    CHECK(output_format == AUDIO_S16SYS && output_channels == 2 && output_rate == 44100);
    conversion->needed = 0;
    conversion->len_ratio = 1;
    return 0;
}
static inline void SDL_ConvertAudio(SDL_AudioCVT *conversion)
{
    conversion->len_cvt = conversion->len;
    memset(conversion->buf, 0x5a, conversion->len_cvt);
}
static inline void pcm_copy_buffer(void *destination, const void *source, size_t bytes)
{
    memcpy(destination, source, bytes);
}
static inline void panicf(const char *format, ...) { (void)format; CHECK(false); }
static void sdl_audio_callback(void *context, Uint8 *stream, int length)
{
    (void)context;
    (void)stream;
    (void)length;
}

#define DEBUGF trace_log
#define printf trace_log
#define fopen mock_fopen
#define fwrite mock_fwrite
#define fclose mock_fclose
#define ferror mock_ferror
#include "actual_audio_debug.h"
#undef printf

static bool parse_option(const char *argument)
{
    const char *arguments[] = {argument};
    const int argument_index = 0;
    bool recognized = true;
#define printf trace_log
#include "actual_audio_option.h"
    if (!strcmp(arguments[argument_index], "--other"))
        recognized = false;
    else
        recognized = false;
#undef printf
    return recognized;
}

static void prepare(void)
{
    sink_dma_init();
    sink_set_freq_nolock(0);
    memset(input, 0x31, sizeof(input));
    memset(output, 0xcc, sizeof(output));
    pcm_data = input;
    udata.stream = output;
    udata.num_in = 8;
    udata.num_out = 4;
}

int main(int argument_count, char **arguments)
{
    CHECK(argument_count == 2);
    const char *scenario = arguments[1];
    if (!strcmp(scenario, "default"))
    {
        CHECK(!parse_option("--other"));
        prepare();
        write_to_soundcard(&udata);
        sink_dma_stop();
        CHECK(opens == 0 && writes == 0 && closes == 0 && errors == 0);
        CHECK(strstr(logs, "Audio debug") == NULL);
        return 0;
    }
#if defined(DEBUG) || defined(SIMULATOR)
    CHECK(!debug_audio);
    CHECK(parse_option("--debugaudio") && debug_audio);
    if (!strcmp(scenario, "open-failure"))
        open_failure = true;
    prepare();
#ifdef WIN32
    CHECK(!strcmp(last_mode, "wbN"));
#else
    CHECK(!strcmp(last_mode, "wbe"));
#endif
    if (!strcmp(scenario, "open-failure"))
    {
        CHECK(!debug_audio && udata.debug == NULL);
        CHECK(strstr(logs, "Audio debug file open failed\n") != NULL);
        CHECK(strstr(logs, "Audio debug file open\n") == NULL);
        for (int attempt = 0; attempt < 30; ++attempt)
            write_to_soundcard(&udata);
        CHECK(opens == 1 && writes == 0);
        return 0;
    }
    CHECK(strstr(logs, "Audio debug format: rate=44100 format=32784 channels=2 frame_bytes=4\n") != NULL);
    if (!strcmp(scenario, "reopen") || !strcmp(scenario, "append-failure"))
    {
        sink_dma_stop();
        open_failure = !strcmp(scenario, "append-failure");
        write_to_soundcard(&udata);
#ifdef WIN32
        CHECK(!strcmp(last_mode, "abN"));
#else
        CHECK(!strcmp(last_mode, "abe"));
#endif
        CHECK(opens == 2);
        if (open_failure)
        {
            CHECK(!debug_audio && writes == 0);
            write_to_soundcard(&udata);
            CHECK(opens == 2);
            return 0;
        }
    }
    if (!strcmp(scenario, "short-write"))
        short_write = true;
    if (!strcmp(scenario, "stream-error"))
        stream_failure = true;
    if (!strcmp(scenario, "close-failure"))
        close_failure = true;
    if (!strcmp(scenario, "converted"))
    {
        cvt.needed = 1;
        cvt.len_mult = 1;
        cvt.len_ratio = 1;
        cvt_status = 1;
    }
    if (!strcmp(scenario, "fallback-u8") || !strcmp(scenario, "fallback-s16"))
    {
        cvt.needed = 1;
        cvt_status = -1;
        obtained.silence = !strcmp(scenario, "fallback-u8") ? 0x80 : 0;
        pcm_channel_bytes = obtained.silence ? 1 : 2;
        pcm_sample_bytes = pcm_channel_bytes * obtained.channels;
    }
    write_to_soundcard(&udata);
    if (short_write || stream_failure)
    {
        CHECK(!debug_audio && udata.debug == NULL && closes == 1);
        CHECK(strstr(logs, "Audio debug file write failed\n") != NULL);
        write_to_soundcard(&udata);
        CHECK(opens == 1 && writes == 1);
        return 0;
    }
    CHECK(trace_bytes == udata.num_out * pcm_sample_bytes);
    CHECK(trace_bytes == 4 * pcm_sample_bytes);
    if (!strcmp(scenario, "converted"))
        CHECK(trace[0] == 0x5a && trace[trace_bytes - 1] == 0x5a);
    else if (cvt.needed)
        CHECK(!memcmp(trace, output, trace_bytes));
    else
        CHECK(!memcmp(trace, input, trace_bytes));
    sink_dma_stop();
    CHECK(udata.debug == NULL);
    if (close_failure)
    {
        CHECK(!debug_audio);
        CHECK(strstr(logs, "Audio debug file close failed\n") != NULL);
        CHECK(strstr(logs, "Audio debug file closed\n") == NULL);
    }
    else
        CHECK(strstr(logs, "Audio debug file closed\n") != NULL);
#else
    CHECK(!parse_option("--debugaudio"));
    prepare();
    write_to_soundcard(&udata);
    sink_dma_stop();
    CHECK(!opens && !writes && !closes);
#endif
    return 0;
}
