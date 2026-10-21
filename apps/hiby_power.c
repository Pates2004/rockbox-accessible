#include "config.h"
#include "hiby_power.h"
#include "kernel.h"
#include "lang.h"
#include "language.h"
#include "list.h"
#include "menu.h"
#include "settings.h"
#include "splash.h"
#include "talk.h"
#include <stdio.h>

#if !defined(SIMULATOR) && !defined(BOOTLOADER)
#include "power-control-hiby.h"
static struct hiby_wifi_result startup_wifi;
static bool startup_checked;
#endif

static const int status_labels[] = {
    LANG_HIBY_WIFI_STARTUP_STATE, LANG_HIBY_WIFI_RADIOS, LANG_HIBY_WIFI_INTERFACES,
    LANG_HIBY_WIFI_RADIO_ERROR, LANG_HIBY_WIFI_INTERFACE_ERROR
};

static unsigned int status_count(void)
{
#if defined(SIMULATOR) || defined(BOOTLOADER)
    return 1;
#else
    return sizeof(status_labels) / sizeof(status_labels[0]);
#endif
}

void hiby_power_init(void)
{
#if !defined(SIMULATOR) && !defined(BOOTLOADER)
    startup_wifi = hiby_wifi_disable();
    startup_checked = true;
#endif
}

static int startup_state_label(void)
{
#if !defined(SIMULATOR) && !defined(BOOTLOADER)
    if (startup_checked && startup_wifi.state == HIBY_WIFI_BLOCKED)
        return LANG_HIBY_WIFI_BLOCKED;
    if (startup_checked && startup_wifi.state == HIBY_WIFI_NO_RADIO)
        return LANG_HIBY_WIFI_NO_RADIO;
    if (startup_checked && startup_wifi.state == HIBY_WIFI_INTERFACE_DOWN)
        return LANG_HIBY_WIFI_INTERFACE_DOWN;
    if (startup_checked && startup_wifi.state == HIBY_WIFI_DRIVER_SUSPENDED)
        return LANG_HIBY_WIFI_DRIVER_SUSPENDED;
    if (startup_checked && startup_wifi.state == HIBY_WIFI_ERROR)
        return LANG_HIBY_WIFI_CONTROL_FAILED;
    return LANG_HIBY_WIFI_UNCONFIRMED;
#else
    return LANG_HIBY_WIFI_SIMULATOR;
#endif
}

void hiby_power_startup_notice(void)
{
#if !defined(SIMULATOR) && !defined(BOOTLOADER)
    if (startup_state_label() != LANG_HIBY_WIFI_BLOCKED &&
        startup_state_label() != LANG_HIBY_WIFI_DRIVER_SUSPENDED)
        splash(3 * HZ, ID2P(startup_state_label()));
#endif
}

static int startup_value(int selected)
{
#if !defined(SIMULATOR) && !defined(BOOTLOADER)
    switch (selected)
    {
        case 1: return startup_wifi.wlan_radios;
        case 2: return startup_wifi.interfaces_down;
        case 3: return startup_wifi.rfkill_error;
        case 4: return startup_wifi.interface_error;
    }
#else
    (void)selected;
#endif
    return 0;
}

static const char *status_name(int selected, void *data, char *buffer, size_t length)
{
    (void)data;
    if (selected < 0 || (unsigned int)selected >= status_count())
    {
        if (length)
            buffer[0] = '\0';
        return buffer;
    }
    if (selected == 0)
        snprintf(buffer, length, "%s: %s", str(status_labels[selected]), str(startup_state_label()));
    else
        snprintf(buffer, length, "%s: %d", str(status_labels[selected]), startup_value(selected));
    return buffer;
}

static int status_speak(int selected, void *data)
{
    (void)data;
    if (selected < 0 || (unsigned int)selected >= status_count())
        return 0;
    talk_id(status_labels[selected], false);
    if (selected == 0)
        talk_id(startup_state_label(), true);
    else
        talk_number(startup_value(selected), true);
    return 0;
}

int hiby_power_status_menu(void)
{
    struct simplelist_info list;
    simplelist_info_init(&list, str(LANG_HIBY_WIFI_STARTUP),
        status_count(), NULL);
    list.get_name = status_name;
    list.get_talk = status_speak;
    return simplelist_show_list(&list) ? MENU_ATTACHED_USB : 0;
}
