#include "config.h"
#include "accessibility_touch.h"

#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)

#include <limits.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include "accessibility.h"
#include "file.h"
#include "kernel.h"
#include "lang.h"
#include "menu.h"
#include "rbpaths.h"
#include "settings.h"
#include "splash.h"
#include "talk.h"

#define TOUCH_SETTINGS_FILE ROCKBOX_DIR "/touch-sensitivity.cfg"
#define TOUCH_SETTINGS_TEMP ROCKBOX_DIR "/touch-sensitivity.cfg.tmp"
#define TOUCH_SETTINGS_HEADER "RBTOUCH-SENSITIVITY:1\npercent:"

static bool sensitivity_loaded;
static unsigned int sensitivity = 100;

static void sensitivity_load(void)
{
    if (sensitivity_loaded)
        return;
    sensitivity_loaded = true;
    int descriptor = open(TOUCH_SETTINGS_FILE, O_RDONLY);
    if (descriptor < 0)
        return;
    char data[64];
    size_t used = 0;
    bool valid = true;
    while (used < sizeof(data) - 1)
    {
        ssize_t count = read(descriptor, data + used, sizeof(data) - 1 - used);
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
    data[used] = '\0';
    const size_t prefix = sizeof(TOUCH_SETTINGS_HEADER) - 1;
    if (!valid || used < prefix + 3 || used > prefix + 4 ||
        memcmp(data, TOUCH_SETTINGS_HEADER, prefix) || data[used - 1] != '\n')
        return;
    unsigned int value = 0;
    for (size_t offset = prefix; offset + 1 < used; ++offset)
    {
        if (data[offset] < '0' || data[offset] > '9')
            return;
        value = value * 10 + (unsigned int)(data[offset] - '0');
    }
    if (value >= 50 && value <= 200 && value % 25 == 0)
        sensitivity = value;
}

static bool sensitivity_save(unsigned int value)
{
    if (value < 50 || value > 200 || value % 25 != 0)
        return false;
    char data[64];
    int length = snprintf(data, sizeof(data), TOUCH_SETTINGS_HEADER "%u\n", value);
    if (length <= 0 || (size_t)length >= sizeof(data))
        return false;
    int descriptor = open(TOUCH_SETTINGS_TEMP, O_WRONLY | O_CREAT | O_TRUNC, 0666);
    if (descriptor < 0)
        return false;
    size_t written = 0;
    bool valid = true;
    while (written < (size_t)length)
    {
        ssize_t count = write(descriptor, data + written, (size_t)length - written);
        if (count <= 0)
        {
            valid = false;
            break;
        }
        written += count;
    }
    if (valid && fsync(descriptor) != 0)
        valid = false;
    if (close(descriptor) != 0)
        valid = false;
    if (!valid || rename(TOUCH_SETTINGS_TEMP, TOUCH_SETTINGS_FILE) != 0)
    {
        remove(TOUCH_SETTINGS_TEMP);
        return false;
    }
    sensitivity = value;
    sensitivity_loaded = true;
    return true;
}

unsigned int accessibility_touch_distance(unsigned int normal_distance)
{
    sensitivity_load();
    unsigned int quotient = normal_distance / sensitivity;
    unsigned int remainder = normal_distance % sensitivity;
    if (quotient > UINT_MAX / 100)
        return UINT_MAX;
    unsigned int scaled = quotient * 100;
    unsigned int fraction = (remainder * 100 + sensitivity / 2) / sensitivity;
    if (scaled > UINT_MAX - fraction)
        return UINT_MAX;
    scaled += fraction;
    return scaled ? scaled : 1;
}

int accessibility_touch_sensitivity_menu(void)
{
    sensitivity_load();
    int choice = sensitivity;
    if (set_int((const unsigned char *)str(LANG_TOUCH_GESTURE_SENSITIVITY), "%",
                UNIT_PERCENT, &choice, NULL, 25, 50, 200, NULL))
        return MENU_ATTACHED_USB;
    if (choice != (int)sensitivity)
    {
        if (!sensitivity_save(choice))
            splash(HZ * 2, ID2P(LANG_ERROR_WRITING_CONFIG));
        else
            accessibility_init();
    }
    return 0;
}

#else

unsigned int accessibility_touch_distance(unsigned int normal_distance)
{
    return normal_distance;
}
int accessibility_touch_sensitivity_menu(void) { return 0; }

#endif
