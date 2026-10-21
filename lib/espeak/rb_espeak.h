#ifndef RB_ESPEAK_H
#define RB_ESPEAK_H

#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

enum rb_espeak_result {
    RB_ESPEAK_OK = 0,
    RB_ESPEAK_ABORTED = 1,
    RB_ESPEAK_ERROR = -1,
    RB_ESPEAK_INVALID_VOICE = -2,
    RB_ESPEAK_NOT_INITIALIZED = -3,
    RB_ESPEAK_INVALID_ARGUMENT = -4,
    RB_ESPEAK_BUSY = -5
};

typedef int (*rb_espeak_callback)(const short *samples, int count, void *user);
typedef void (*rb_espeak_position_callback)(int character, int milliseconds,
                                           void *user);

enum rb_espeak_punctuation {
    RB_ESPEAK_PUNCT_NONE = 0,
    RB_ESPEAK_PUNCT_SOME = 1,
    RB_ESPEAK_PUNCT_MOST = 2,
    RB_ESPEAK_PUNCT_ALL = 3
};

int rb_espeak_init(const char *data_parent);
int rb_espeak_synth(const char *text, const char *language,
                   const char *variant, int rate, int pitch, int volume,
                   int range, int wordgap, int punctuation,
                   rb_espeak_callback callback, void *user);
int rb_espeak_synth_tracked(const char *text, const char *language,
                   const char *variant, int rate, int pitch, int volume,
                   int range, int wordgap, int punctuation,
                   rb_espeak_callback callback,
                   rb_espeak_position_callback position_callback, void *user);
int rb_espeak_synth_character(unsigned int character, const char *language,
                   const char *variant, int rate, int pitch, int volume,
                   int range, int wordgap, rb_espeak_callback callback, void *user);
int rb_espeak_voice_count(bool variants);
const char *rb_espeak_voice_name(bool variants, int index);
const char *rb_espeak_voice_id(bool variants, int index);
int rb_espeak_validate_voice(const char *language, const char *variant);

#ifdef __cplusplus
}
#endif

#endif
