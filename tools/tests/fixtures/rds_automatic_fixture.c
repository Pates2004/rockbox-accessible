#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#define HZ 100
#define AUDIO_STATUS_RECORD 4
#define CHECK(c) do { if (!(c)) { fprintf(stderr, "line %d: %s\n", __LINE__, #c); exit(101); } } while (0)
enum { FMRADIO_OFF, FMRADIO_PLAYING, FMRADIO_PAUSED };
enum { RADIO_RDS_NAME, RADIO_RDS_TEXT, LANG_FM_RDS_NAME, LANG_FM_RDS_TEXT, LANG_FM_RDS_NO_DATA };
struct user_settings { int fm_rds_talk; bool tts_enabled, tts_announce_dynamic, talk_menu; };
static struct user_settings global_settings;
static unsigned long current_tick;
static int status, recording, id_count, text_count, cancels;
static bool present, busy, available;
static const char *name_data = "Station", *text_data = "Artist - Title";
static char said[32][193];
static int labels[32];
static bool enqueues[32];
static int get_radio_status(void) { return status; }
static bool radio_hardware_present(void) { return present; }
static bool tts_is_available(void) { return available && global_settings.tts_enabled; }
static bool tts_is_busy(void) { return busy; }
static int audio_status(void) { return recording; }
static size_t strlcpy(char *out, const char *in, size_t size)
{
    size_t length = strlen(in);
    if (size) { size_t n = length < size - 1 ? length : size - 1; memcpy(out, in, n); out[n] = 0; }
    return length;
}
static bool tuner_get_rds_info(int field, char *out, size_t size)
{
    strlcpy(out, field == RADIO_RDS_NAME ? name_data : text_data, size);
    return true;
}
static void talk_cancel_enqueue_next(void) { cancels++; }
static void talk_id(int label, bool enqueue)
{
    CHECK(id_count < 32); labels[id_count] = label; enqueues[id_count++] = enqueue;
}
static void talk_spell(const char *text, bool enqueue)
{
    CHECK(enqueue && text_count < 32); strlcpy(said[text_count++], text, sizeof(said[0]));
}
ACTUAL_POLICY
ACTUAL_RDS

static struct radio_rds_speech state;
static int frequency = 100000000;
static void step(unsigned long elapsed, bool idle, bool searching)
{
    current_tick += elapsed;
    radio_rds_speech_update(&state, frequency, idle, searching);
}
static void settle(void) { step(50, true, false); step(200, true, false); }

int main(int argc, char **argv)
{
    CHECK(argc == 2);
    const char *scenario = argv[1];
    global_settings = (struct user_settings){3, true, true, false};
    status = FMRADIO_PLAYING; present = available = true;
    if (!strcmp(scenario, "wrap")) current_tick = ULONG_MAX - 120;
    step(0, true, false);
    settle();
    CHECK(text_count == 2 && id_count == 2 && cancels == 1);
    CHECK(labels[0] == LANG_FM_RDS_NAME && labels[1] == LANG_FM_RDS_TEXT);
    CHECK(!enqueues[0] && enqueues[1]);
    CHECK(!strcmp(said[0], "Station") && !strcmp(said[1], "Artist - Title"));
    if (!strcmp(scenario, "manual"))
    {
        global_settings.tts_announce_dynamic = false; busy = true; text_data = "Manual title";
        radio_speak_info(); CHECK(text_count == 4 && id_count == 4);
        CHECK(!strcmp(said[3], "Manual title") && !enqueues[2] && enqueues[3]);
        CHECK(status == FMRADIO_PLAYING && frequency == 100000000);
    }
    else if (!strcmp(scenario, "manual-empty"))
    {
        present = false; radio_speak_info(); CHECK(text_count == 2 && id_count == 6);
        CHECK(labels[3] == LANG_FM_RDS_NO_DATA && labels[5] == LANG_FM_RDS_NO_DATA);
    }
    else if (!strcmp(scenario, "normal") || !strcmp(scenario, "wrap"))
    {
        step(5000, true, false); CHECK(text_count == 2);
        text_data = "New title"; step(50, true, false); settle();
        CHECK(text_count == 3 && !strcmp(said[2], "New title"));
    }
    else if (!strcmp(scenario, "throttle"))
    {
        text_data = "New title"; step(50, true, false); settle(); CHECK(text_count == 2);
        step(750, true, false); CHECK(text_count == 3);
    }
    else if (!strcmp(scenario, "busy"))
    {
        busy = true; text_data = "Intermediate"; step(1000, true, false); settle();
        text_data = "Latest"; step(50, true, false); settle(); CHECK(text_count == 2);
        busy = false; step(50, true, false); CHECK(text_count == 3 && !strcmp(said[2], "Latest"));
    }
    else if (!strcmp(scenario, "unstable"))
    {
        for (int i = 0; i < 30; i++) { text_data = i % 2 ? "One" : "Two"; step(50, true, false); }
        CHECK(text_count == 2); settle(); CHECK(text_count == 3);
    }
    else if (!strcmp(scenario, "blank"))
    {
        text_data = ""; name_data = ""; step(2000, true, false); settle(); CHECK(text_count == 2);
        text_data = "Artist - Title"; name_data = "Station"; step(50, true, false); settle(); CHECK(text_count == 2);
    }
    else if (!strcmp(scenario, "input"))
    {
        text_data = "New title"; step(2000, false, false); settle(); CHECK(text_count == 3);
        CHECK(!strcmp(said[2], "New title"));
    }
    else if (!strcmp(scenario, "retune"))
    {
        frequency += 100000; name_data = "Second"; text_data = "";
        step(50, true, false); CHECK(text_count == 2); settle();
        CHECK(text_count == 3 && !strcmp(said[2], "Second"));
    }
    else if (!strcmp(scenario, "modes"))
    {
        global_settings.fm_rds_talk = 1; step(50, true, false); settle(); CHECK(text_count == 3);
        text_data = "Other"; step(2000, true, false); settle(); CHECK(text_count == 3);
        global_settings.fm_rds_talk = 2; step(50, true, false); settle();
        CHECK(text_count == 4 && !strcmp(said[3], "Other"));
    }
    else if (!strcmp(scenario, "long"))
    {
        static char long_text[300]; memset(long_text, 'x', 299); text_data = long_text;
        step(2000, true, false); settle(); CHECK(text_count == 3 && strlen(said[2]) == 192);
    }
    else
    {
        if (!strcmp(scenario, "paused")) status = FMRADIO_PAUSED;
        else if (!strcmp(scenario, "off")) status = FMRADIO_OFF;
        else if (!strcmp(scenario, "disabled")) global_settings.fm_rds_talk = 0;
        else if (!strcmp(scenario, "invalid")) global_settings.fm_rds_talk = 4;
        else if (!strcmp(scenario, "dynamic")) global_settings.tts_announce_dynamic = false;
        else if (!strcmp(scenario, "synthesis")) global_settings.tts_enabled = false;
        else if (!strcmp(scenario, "unavailable")) available = false;
        else if (!strcmp(scenario, "missing")) present = false;
        else if (!strcmp(scenario, "recording")) recording = AUDIO_STATUS_RECORD;
        else if (strcmp(scenario, "searching")) CHECK(false);
        text_data = "Do not say";
        step(2000, true, !strcmp(scenario, "searching"));
        step(2000, true, !strcmp(scenario, "searching")); CHECK(text_count == 2);
    }
    puts("PASS"); return 0;
}
