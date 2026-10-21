#ifndef HIBY_BLUETOOTH_SERVICE_FRAMEWORK_H
#define HIBY_BLUETOOTH_SERVICE_FRAMEWORK_H

#include <stdbool.h>
#include <stddef.h>
#include "hiby_bluetooth_service_language.h"

#define HZ 100
#ifndef DEFAULT_STACK_SIZE
#define DEFAULT_STACK_SIZE 8192
#endif
#ifndef MAX
#define MAX(first, second) ((first) > (second) ? (first) : (second))
#endif
#ifndef IF_PRIO
#define IF_PRIO(...)
#endif
#ifndef IF_COP
#define IF_COP(...)
#endif
#define AUDIO_STATUS_PLAY 1u
#define AUDIO_STATUS_PAUSE 2u

struct service_test_settings
{
    bool menus;
    bool dynamic;
};

extern struct service_test_settings global_settings;
unsigned int service_test_create_thread(void (*entry)(void), void *stack,
    size_t stack_size, unsigned int flags, const char *name);
void service_test_thread_wait(unsigned int identifier);
void service_test_sleep(int ticks);
bool button_queue_empty(void);
unsigned int audio_status(void);
void audio_pause(void);
unsigned int audio_playback_generation(void);
bool audio_pause_guarded(unsigned int generation, bool (*begin)(void *context),
    void (*end)(void *context), void *context);
void audio_resume(void);
bool talk_menus_enabled(const struct service_test_settings *settings);
bool talk_dynamic_enabled(const struct service_test_settings *settings);
int talk_id(int identifier, bool enqueue);
int talk_spell(const char *text, bool enqueue);
bool tts_is_available(void);
bool tts_speak(const char *text, size_t length, bool enqueue);

#ifndef HIBY_BT_REAL_FRAMEWORK_TEST
#define create_thread service_test_create_thread
#define thread_wait service_test_thread_wait
#define sleep service_test_sleep
#endif

#endif
