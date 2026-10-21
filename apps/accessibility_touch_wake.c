#include "accessibility_touch_wake.h"

#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && \
    !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)

#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "accessibility_touch.h"
#include "action.h"
#include "file.h"
#include "kernel.h"
#include "lang.h"
#include "list.h"
#include "menu.h"
#include "rbpaths.h"
#include "settings.h"
#include "splash.h"
#include "talk.h"
#include "touchscreen.h"

#define TOUCH_WAKE_FILE ROCKBOX_DIR "/touch-wake.cfg"
#define TOUCH_WAKE_TEMP ROCKBOX_DIR "/touch-wake.cfg.tmp"
#define TOUCH_WAKE_DEFAULT "RBTOUCH-WAKE:1\nsingle:0\ndouble:0\ntriple:0\n"
#define TOUCH_WAKE_GAP_MS 320u
#define TOUCH_WAKE_TAP_MS 300u

static bool wake_loaded;
static uint8_t wake_actions[3];
static bool wake_active;
static bool wake_contact;
static bool wake_invalid;
static bool wake_locked;
static int wake_context;
static unsigned int wake_taps;
static int wake_x, wake_y;
static uint32_t wake_pressed_ms, wake_released_ms;

void accessibility_touch_wake_cancel(void)
{
    wake_active = false;
    wake_contact = false;
    wake_invalid = false;
    wake_taps = 0;
}

static void wake_load(void)
{
    if (wake_loaded)
        return;
    wake_loaded = true;
    char data[sizeof(TOUCH_WAKE_DEFAULT)];
    size_t used = 0;
    bool valid = true;
    int descriptor = open(TOUCH_WAKE_FILE, O_RDONLY);
    if (descriptor >= 0)
    {
        unsigned int interrupted = 0;
        while (used < sizeof(data))
        {
            ssize_t count = read(descriptor, data + used, sizeof(data) - used);
            if (count < 0 && errno == EINTR && ++interrupted < 4)
                continue;
            if (count < 0)
            {
                valid = false;
                break;
            }
            if (!count)
                break;
            used += count;
        }
        if (close(descriptor) != 0)
            valid = false;
        const size_t positions[] = {
            sizeof("RBTOUCH-WAKE:1\nsingle:") - 1,
            sizeof("RBTOUCH-WAKE:1\nsingle:0\ndouble:") - 1,
            sizeof("RBTOUCH-WAKE:1\nsingle:0\ndouble:0\ntriple:") - 1
        };
        uint8_t actions[3] = {0};
        if (valid && used == sizeof(TOUCH_WAKE_DEFAULT) - 1)
        {
            for (unsigned int index = 0; index < 3; ++index)
            {
                unsigned char value = data[positions[index]];
                if (value < '0' || value > '2')
                    valid = false;
                actions[index] = value - '0';
                data[positions[index]] = '0';
            }
            if (valid && !memcmp(data, TOUCH_WAKE_DEFAULT, used))
                memcpy(wake_actions, actions, sizeof(wake_actions));
        }
    }
    touchscreen_set_wake_enabled(wake_actions[0] || wake_actions[1] || wake_actions[2]);
}

bool accessibility_touch_wake_enabled(void)
{
    wake_load();
    return wake_actions[0] || wake_actions[1] || wake_actions[2];
}

int accessibility_touch_wake_timeout(int timeout)
{
    wake_load();
    int interval = HZ / 20 > 0 ? HZ / 20 : 1;
    return wake_active && !wake_contact && (timeout < 0 || timeout > interval) ? interval : timeout;
}

static uint32_t wake_milliseconds(long tick)
{
#if 1000 % HZ == 0
    return (uint32_t)tick * (1000 / HZ);
#else
    return (uint32_t)((uint64_t)(uint32_t)tick * 1000 / HZ);
#endif
}

static enum accessibility_touch_wake_result wake_complete(bool swallow_contact)
{
    unsigned int action = wake_taps && wake_taps <= 3 ? wake_actions[wake_taps - 1] : 0;
    accessibility_touch_wake_cancel();
    wake_active = wake_contact = wake_invalid = swallow_contact;
    return action == 2 ? ACCESSIBILITY_TOUCH_WAKE_UNLOCK :
        action == 1 ? ACCESSIBILITY_TOUCH_WAKE_LIGHT : ACCESSIBILITY_TOUCH_WAKE_CONSUMED;
}

enum accessibility_touch_wake_result accessibility_touch_wake_process(
    const struct touchevent *event, bool locked, bool dark, int context)
{
    if (!accessibility_touch_wake_enabled())
        return ACCESSIBILITY_TOUCH_WAKE_PASS;
    if (!wake_active && (!locked && !dark))
        return ACCESSIBILITY_TOUCH_WAKE_PASS;
    if (wake_active && (wake_context != context || wake_locked != locked || (!locked && !dark)))
    {
        wake_invalid = true;
        wake_taps = 0;
    }
    uint32_t now = wake_milliseconds(event ? event->tick : current_tick);
    if (!event || event->type == TOUCHEVENT_NONE)
    {
        if (!wake_active)
            return ACCESSIBILITY_TOUCH_WAKE_PASS;
        if (wake_contact && now - wake_pressed_ms > TOUCH_WAKE_TAP_MS)
        {
            wake_invalid = true;
            wake_taps = 0;
        }
        if (!wake_contact && now - wake_released_ms > TOUCH_WAKE_GAP_MS)
            return wake_complete(false);
        return ACCESSIBILITY_TOUCH_WAKE_CONSUMED;
    }
    if (event->type == TOUCHEVENT_PRESS)
    {
        if (wake_active && !wake_contact && now - wake_released_ms > TOUCH_WAKE_GAP_MS)
            return wake_complete(true);
        if (!wake_active)
        {
            wake_context = context;
            wake_locked = locked;
        }
        else if (wake_contact)
            wake_invalid = true;
        wake_active = wake_contact = true;
        wake_pressed_ms = now;
        wake_x = event->x;
        wake_y = event->y;
    }
    else if (wake_contact && (event->type == TOUCHEVENT_CONTACT || event->type == TOUCHEVENT_RELEASE))
    {
        int horizontal = event->x - wake_x;
        int vertical = event->y - wake_y;
        int slop = accessibility_touch_distance(12);
        if (horizontal < -slop || horizontal > slop || vertical < -slop || vertical > slop ||
            now - wake_pressed_ms > TOUCH_WAKE_TAP_MS)
            wake_invalid = true;
        if (event->type == TOUCHEVENT_RELEASE)
        {
            wake_contact = false;
            if (wake_invalid)
            {
                accessibility_touch_wake_cancel();
                return ACCESSIBILITY_TOUCH_WAKE_CONSUMED;
            }
            ++wake_taps;
            wake_released_ms = now;
            if (wake_taps == 3)
                return wake_complete(false);
        }
    }
    return ACCESSIBILITY_TOUCH_WAKE_CONSUMED;
}

static bool wake_save(const uint8_t *actions)
{
    if (actions[0] > 2 || actions[1] > 2 || actions[2] > 2)
        return false;
    char data[sizeof(TOUCH_WAKE_DEFAULT)];
    int length = snprintf(data, sizeof(data), "RBTOUCH-WAKE:1\nsingle:%u\ndouble:%u\ntriple:%u\n",
        (unsigned int)actions[0], (unsigned int)actions[1], (unsigned int)actions[2]);
    if (length != (int)sizeof(TOUCH_WAKE_DEFAULT) - 1)
        return false;
    int descriptor = open(TOUCH_WAKE_TEMP, O_WRONLY | O_CREAT | O_EXCL, 0666);
    if (descriptor < 0)
        return false;
    size_t used = 0;
    unsigned int interrupted = 0;
    bool valid = true;
    while (used < (size_t)length)
    {
        ssize_t count = write(descriptor, data + used, length - used);
        if (count < 0 && errno == EINTR && ++interrupted < 4)
            continue;
        if (count <= 0)
        {
            valid = false;
            break;
        }
        used += count;
    }
    if (valid && fsync(descriptor) != 0)
        valid = false;
    if (close(descriptor) != 0)
        valid = false;
    if (!valid || rename(TOUCH_WAKE_TEMP, TOUCH_WAKE_FILE) != 0)
    {
        remove(TOUCH_WAKE_TEMP);
        return false;
    }
    memcpy(wake_actions, actions, sizeof(wake_actions));
    wake_loaded = true;
    accessibility_touch_wake_cancel();
    touchscreen_set_wake_enabled(actions[0] || actions[1] || actions[2]);
    action_update_touch_lock();
    return true;
}

static const int wake_gesture_labels[] = {
    LANG_TOUCH_WAKE_SINGLE, LANG_TOUCH_WAKE_DOUBLE, LANG_TOUCH_WAKE_TRIPLE
};
static const int wake_action_labels[] = {LANG_OFF, LANG_TOUCH_WAKE_LIGHT, LANG_TOUCH_WAKE_UNLOCK};

static const char *wake_name(int selected, void *data, char *buffer, size_t length)
{
    (void)data;
    snprintf(buffer, length, "%s: %s", str(wake_gesture_labels[selected]),
             str(wake_action_labels[wake_actions[selected]]));
    return buffer;
}

static int wake_speak(int selected, void *data)
{
    (void)data;
    talk_id(wake_gesture_labels[selected], false);
    talk_id(wake_action_labels[wake_actions[selected]], true);
    return 0;
}

int accessibility_touch_wake_menu(void)
{
    wake_load();
    int selection = 0;
    for (;;)
    {
        struct simplelist_info list;
        simplelist_info_init(&list, str(LANG_TOUCH_WAKE_SETTINGS), 3, NULL);
        list.selection = selection;
        list.get_name = wake_name;
        list.get_talk = wake_speak;
        if (simplelist_show_list(&list))
            return MENU_ATTACHED_USB;
        selection = list.selection;
        if (selection < 0)
            return 0;
        if (selection >= 3)
            continue;
        int choice = wake_actions[selection];
        struct opt_items options[3];
        for (unsigned int index = 0; index < 3; ++index)
            options[index] = (struct opt_items){
                (const unsigned char *)str(wake_action_labels[index]), wake_action_labels[index]
            };
        if (set_option(str(wake_gesture_labels[selection]), &choice, RB_INT, options, 3, NULL))
            return MENU_ATTACHED_USB;
        if (choice != wake_actions[selection])
        {
            uint8_t actions[3];
            memcpy(actions, wake_actions, sizeof(actions));
            actions[selection] = choice;
            if (!wake_save(actions))
                splash(HZ * 2, ID2P(LANG_ERROR_WRITING_CONFIG));
        }
    }
}
#endif
