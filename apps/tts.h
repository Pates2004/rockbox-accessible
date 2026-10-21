#ifndef ROCKBOX_TTS_H
#define ROCKBOX_TTS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

enum tts_rate_scale {
    TTS_RATE_PERCENT = 0,
    TTS_RATE_WPM
};

bool tts_init(void);
bool tts_is_available(void);
bool tts_output_uses_synthesis(void);
bool tts_is_busy(void);
int tts_speak(const char *text, size_t length, bool enqueue);
int tts_speak_tracked(const char *text, size_t length);
int tts_speak_character(uint32_t codepoint);
int tts_speak_character_options(uint32_t codepoint, bool enqueue, int pitch_percent);
size_t tts_read_position(void);
bool tts_read_interrupted(void);
void tts_pause(bool paused);
bool tts_request_cancelled(uint32_t expected);
int tts_speak_id(int32_t id, bool enqueue);
const char *tts_get_voice_text(int32_t id);
int tts_speak_status(int32_t id);
int tts_speak_status_ids(const int32_t *ids, size_t count);
void tts_voice_clip_started(void);
void tts_voice_output_finished(void);
void tts_stop(void);
void tts_settings_changed(void);
bool tts_choose_voice(bool variants);
bool tts_read_file(const char *path);
struct text_bookmark;
bool tts_read_bookmark(const char *path, const struct text_bookmark *bookmark);
const char *tts_last_error(void);
const char *tts_last_warning(void);
const char *tts_format_rate(char *buffer, size_t size, int value,
                            const char *unit);
int32_t tts_rate_talk_id(int value, int unit);
void tts_ducking_changed(bool value);
void tts_ducking_level_changed(int value);

#endif
