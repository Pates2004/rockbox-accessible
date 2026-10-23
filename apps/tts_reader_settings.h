/* Private text-reader preferences; main UI context only. */
#ifndef TTS_READER_SETTINGS_H
#define TTS_READER_SETTINGS_H
#include <stdbool.h>

enum tts_reader_wrap
{
    TTS_READER_WRAP_STOP,
    TTS_READER_WRAP_ASK,
    TTS_READER_WRAP_AUTO
};

enum tts_reader_preference
{
    TTS_READER_PREF_MATCH_CASE,
    TTS_READER_PREF_WRAP
};

struct tts_reader_preferences
{
    bool match_case;
    enum tts_reader_wrap wrap;
    int storage_error;
    int cleanup_error;
};

/* Positive errno on failure; effective values remain available in out. */
int tts_reader_preferences_get(struct tts_reader_preferences *out);
int tts_reader_preferences_set(enum tts_reader_preference preference, int value);

#endif
