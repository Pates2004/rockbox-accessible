#include <assert.h>
#include <ctype.h>
#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include "settings_list.h"

#define HAVE_LCD_COLOR
#define RGB565 1
#define RGB565SWAPPED 2
#define RGB888 3
#define XRGB8888 4
#define logf(...) ((void)0)
#define INT_DIGITS 19
#define INT(value) {.int_ = value}
#define UNUSED {.RESERVED = NULL}
#define SYNCLIST_CURSOR_COLOR 2

static uint16_t swap16(uint16_t value) __attribute__((unused));
static uint16_t swap16(uint16_t value)
{
    return (uint16_t)((value >> 8) | (value << 8));
}

#include "actual_lcd_colors.h"

struct settings_fixture
{
    int fg_color;
    int bg_color;
    int lss_color;
    int lse_color;
    int lst_color;
    int list_separator_color;
    int cursor_style;
    unsigned char sbs_file[33];
    unsigned char backdrop_file[81];
    unsigned char colors_file[33];
    unsigned char ui_vp_config[64];
    int statusbar;
    int remote_statusbar;
    int brightness;
    int backlight_timeout;
    int volume;
    int accessibility;
    unsigned char wps_file[33];
    unsigned char fms_file[33];
    unsigned char font_file[33];
    unsigned char icon_file[33];
    unsigned char rsbs_file[33];
    unsigned char remote_ui_vp_config[64];
};

static struct settings_fixture global_settings;
static struct settings_fixture saved_settings;
static char apply_calls[32];
static size_t apply_count;
static int filetype_overrides;
static int rendered_foreground;
static int rendered_background;
static bool rendered_builtin_statusbar;
static bool rendered_plain_viewport;
static bool rendered_no_backdrop;

#include "actual_color_settings.h"

static const char *const cursor_values =
    "pointer,bar (inverse),bar (color),bar (gradient)";
static const struct choice_setting cursor_choice = {
    NULL, 4, "pointer,bar (inverse),bar (color),bar (gradient)", {.desc = NULL}
};

static const struct filename_setting sbs_filename = { "/.rockbox/wps/", ".sbs", 33 };
static const struct filename_setting backdrop_filename = { NULL, NULL, 81 };
static const struct filename_setting colors_filename = { "/.rockbox/themes/", ".colours", 33 };
static const struct filename_setting viewport_filename = { NULL, NULL, 64 };

const struct settings_list settings[] = {
    ACTUAL_COLOR_SETTINGS
    { F_T_INT | F_CHOICE_SETTING | F_TEMPVAR | F_THEMESETTING,
      &global_settings.cursor_style, -1, INT(ACTUAL_CURSOR_DEFAULT), "selector type",
      {.choice_setting = &cursor_choice} },
    { F_T_UCHARPTR | F_FILENAME | F_THEMESETTING | F_NEEDAPPLY,
      global_settings.sbs_file, -1, {.charptr = "-"}, "sbs",
      {.filename_setting = &sbs_filename} },
    { F_T_UCHARPTR | F_FILENAME | F_THEMESETTING | F_NEEDAPPLY,
      global_settings.backdrop_file, -1, {.charptr = "-"}, "backdrop",
      {.filename_setting = &backdrop_filename} },
    { F_T_UCHARPTR | F_FILENAME | F_THEMESETTING | F_NEEDAPPLY,
      global_settings.colors_file, -1, {.charptr = "-"}, "filetype colours",
      {.filename_setting = &colors_filename} },
    { F_T_UCHARPTR | F_FILENAME | F_THEMESETTING | F_NEEDAPPLY,
      global_settings.ui_vp_config, -1, {.charptr = "-"}, "ui viewport",
      {.filename_setting = &viewport_filename} },
};
const int nb_settings = sizeof(settings) / sizeof(settings[0]);

static int sound_default(int setting)
{
    (void)setting;
    abort();
}

static void record_apply(char operation)
{
    assert(apply_count + 1 < sizeof(apply_calls));
    apply_calls[apply_count++] = operation;
    apply_calls[apply_count] = '\0';
}

static void read_color_theme_file(void)
{
    record_apply('C');
    assert(strcmp((char *)global_settings.colors_file, "-") == 0);
    filetype_overrides = 0;
}

static int settings_save(void)
{
    record_apply('S');
    saved_settings = global_settings;
    return 0;
}

static void settings_apply(bool read_disk)
{
    record_apply('A');
    assert(!read_disk);
    rendered_foreground = global_settings.fg_color;
    rendered_background = global_settings.bg_color;
}

static void settings_apply_skins(void)
{
    record_apply('K');
    rendered_builtin_statusbar = strcmp((char *)global_settings.sbs_file, "-") == 0;
    rendered_plain_viewport = strcmp((char *)global_settings.ui_vp_config, "-") == 0;
    rendered_no_backdrop = strcmp((char *)global_settings.backdrop_file, "-") == 0;
}

#include "actual_settings_functions.h"
#include "actual_appearance.h"

static void initialize_settings(void)
{
    memset(&global_settings, 0x55, sizeof(global_settings));
    strcpy((char *)global_settings.sbs_file, "custom-statusbar");
    strcpy((char *)global_settings.backdrop_file, "/.rockbox/backdrops/picture.bmp");
    strcpy((char *)global_settings.colors_file, "custom-colors");
    strcpy((char *)global_settings.ui_vp_config, "0,0,200,200,1,ffffff,ffffff");
    strcpy((char *)global_settings.wps_file, "custom-playback");
    strcpy((char *)global_settings.fms_file, "custom-radio");
    strcpy((char *)global_settings.font_file, "custom-font");
    strcpy((char *)global_settings.icon_file, "custom-icons");
    strcpy((char *)global_settings.rsbs_file, "custom-remote");
    strcpy((char *)global_settings.remote_ui_vp_config, "0,0,100,30,1,00ff00,000000");
    global_settings.statusbar = 2;
    global_settings.remote_statusbar = 0;
    global_settings.brightness = 17;
    global_settings.backlight_timeout = 5;
    global_settings.volume = -23;
    global_settings.accessibility = 123456;
    saved_settings = global_settings;
    apply_count = 0;
    apply_calls[0] = '\0';
    filetype_overrides = 11;
}

static void check_preserved(const struct settings_fixture *original)
{
    assert(global_settings.statusbar == original->statusbar);
    assert(global_settings.remote_statusbar == original->remote_statusbar);
    assert(global_settings.brightness == original->brightness);
    assert(global_settings.backlight_timeout == original->backlight_timeout);
    assert(global_settings.volume == original->volume);
    assert(global_settings.accessibility == original->accessibility);
    assert(memcmp(global_settings.wps_file, original->wps_file,
                  sizeof(global_settings.wps_file)) == 0);
    assert(memcmp(global_settings.fms_file, original->fms_file,
                  sizeof(global_settings.fms_file)) == 0);
    assert(memcmp(global_settings.font_file, original->font_file,
                  sizeof(global_settings.font_file)) == 0);
    assert(memcmp(global_settings.icon_file, original->icon_file,
                  sizeof(global_settings.icon_file)) == 0);
    assert(memcmp(global_settings.rsbs_file, original->rsbs_file,
                  sizeof(global_settings.rsbs_file)) == 0);
    assert(memcmp(global_settings.remote_ui_vp_config, original->remote_ui_vp_config,
                  sizeof(global_settings.remote_ui_vp_config)) == 0);
#ifndef HAVE_BACKDROP_IMAGE
    assert(memcmp(global_settings.backdrop_file, original->backdrop_file,
                  sizeof(global_settings.backdrop_file)) == 0);
#endif
}

static void check_applied(void)
{
    assert(strcmp(apply_calls, "CSAK") == 0);
    assert(filetype_overrides == 0);
    assert(rendered_foreground == global_settings.fg_color);
    assert(rendered_background == global_settings.bg_color);
    assert(rendered_builtin_statusbar);
    assert(rendered_plain_viewport);
#ifdef HAVE_BACKDROP_IMAGE
    assert(rendered_no_backdrop);
#endif
    assert(memcmp(&saved_settings, &global_settings, sizeof(saved_settings)) == 0);
}

static void check_persistence(void)
{
    char stored[11][128];
    int setting_count = nb_settings;
    assert(setting_count == 11);
    assert(strcmp(cursor_values, cursor_choice.cfg_vals) == 0);

    for (int index = 0; index < setting_count; index++)
        cfg_to_string(&settings[index], stored[index], sizeof(stored[index]));

    memset(&global_settings, 0x22, sizeof(global_settings));
    for (int index = 0; index < setting_count; index++)
    {
        bool theme_changed = false;
        assert(string_to_cfg(settings[index].cfg_name, stored[index], &theme_changed));
        assert(theme_changed);
        char serialized[128];
        cfg_to_string(&settings[index], serialized, sizeof(serialized));
        assert(strcmp(serialized, stored[index]) == 0);
    }

    for (int index = 0; index < 6; index++)
    {
        const int *saved_value = (const int *)((const char *)&saved_settings +
            ((const char *)settings[index].setting - (const char *)&global_settings));
        assert(*(const int *)settings[index].setting == *saved_value);
    }
    assert(global_settings.cursor_style == saved_settings.cursor_style);
    assert(strcmp((char *)global_settings.sbs_file, (char *)saved_settings.sbs_file) == 0);
    assert(strcmp((char *)global_settings.backdrop_file,
                  (char *)saved_settings.backdrop_file) == 0);
    assert(strcmp((char *)global_settings.colors_file, (char *)saved_settings.colors_file) == 0);
    assert(strcmp((char *)global_settings.ui_vp_config,
                  (char *)saved_settings.ui_vp_config) == 0);
}

int main(int argument_count, char **arguments)
{
    assert(argument_count == 2);
    const char *scenario = arguments[1];
    initialize_settings();
    struct settings_fixture original = global_settings;
    intptr_t selected = INTERFACE_APPEARANCE_DARK;

    if (strcmp(scenario, "invalid") == 0)
    {
        assert(apply_interface_appearance((void *)(intptr_t)-1) == 0);
        assert(apply_interface_appearance((void *)(intptr_t)3) == 0);
        assert(apply_interface_appearance((void *)INTPTR_MAX) == 0);
        assert(apply_interface_appearance((void *)INTPTR_MIN) == 0);
        assert(apply_count == 0);
        assert(filetype_overrides == 11);
        assert(memcmp(&global_settings, &original, sizeof(original)) == 0);
        return 0;
    }
    if (strstr(scenario, "light"))
        selected = INTERFACE_APPEARANCE_LIGHT;
    if (strstr(scenario, "default"))
        selected = INTERFACE_APPEARANCE_DEFAULT;

    assert(apply_interface_appearance((void *)selected) == 0);
    check_applied();
    check_preserved(&original);

    if (selected == INTERFACE_APPEARANCE_DEFAULT)
    {
        for (int index = 0; index < COLOR_COUNT; index++)
            assert(*colors[index].setting == find_setting(colors[index].setting)->default_val.int_);
        assert(global_settings.cursor_style == ACTUAL_CURSOR_DEFAULT);
    }
    else
    {
        assert(global_settings.cursor_style == SYNCLIST_CURSOR_COLOR);
        assert(global_settings.lss_color == LCD_RGBPACK(0x1e, 0x4e, 0x79));
        assert(global_settings.lse_color == global_settings.lss_color);
        assert(global_settings.lst_color == LCD_RGBPACK(0xff, 0xff, 0xff));
        if (selected == INTERFACE_APPEARANCE_DARK)
        {
            assert(global_settings.fg_color == LCD_RGBPACK(0xf3, 0xf3, 0xf3));
            assert(global_settings.bg_color == LCD_RGBPACK(0x12, 0x12, 0x12));
            assert(global_settings.list_separator_color == LCD_RGBPACK(0x80, 0x80, 0x80));
        }
        else
        {
            assert(global_settings.fg_color == LCD_RGBPACK(0x12, 0x12, 0x12));
            assert(global_settings.bg_color == LCD_RGBPACK(0xff, 0xff, 0xff));
            assert(global_settings.list_separator_color == LCD_RGBPACK(0x70, 0x70, 0x70));
        }
    }

    if (strcmp(scenario, "repeat") == 0)
    {
        struct settings_fixture first_result = global_settings;
        for (int iteration = 0; iteration < 1000; iteration++)
        {
            apply_count = 0;
            assert(apply_interface_appearance((void *)selected) == 0);
            check_applied();
            assert(memcmp(&global_settings, &first_result, sizeof(first_result)) == 0);
        }
    }

    printf("{\"foreground\":[%d,%d,%d],\"background\":[%d,%d,%d],"
           "\"selection\":[%d,%d,%d],\"selected_text\":[%d,%d,%d],"
           "\"separator\":[%d,%d,%d]}\n",
           RGB_UNPACK_RED(global_settings.fg_color),
           RGB_UNPACK_GREEN(global_settings.fg_color),
           RGB_UNPACK_BLUE(global_settings.fg_color),
           RGB_UNPACK_RED(global_settings.bg_color),
           RGB_UNPACK_GREEN(global_settings.bg_color),
           RGB_UNPACK_BLUE(global_settings.bg_color),
           RGB_UNPACK_RED(global_settings.lss_color),
           RGB_UNPACK_GREEN(global_settings.lss_color),
           RGB_UNPACK_BLUE(global_settings.lss_color),
           RGB_UNPACK_RED(global_settings.lst_color),
           RGB_UNPACK_GREEN(global_settings.lst_color),
           RGB_UNPACK_BLUE(global_settings.lst_color),
           RGB_UNPACK_RED(global_settings.list_separator_color),
           RGB_UNPACK_GREEN(global_settings.list_separator_color),
           RGB_UNPACK_BLUE(global_settings.list_separator_color));

    if (strstr(scenario, "persistence"))
        check_persistence();

    return 0;
}
