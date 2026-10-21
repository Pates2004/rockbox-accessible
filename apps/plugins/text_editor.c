/* Modified for Rockbox Accessible; change notice dated 2026-10-21. */
/***************************************************************************
 *             __________               __   ___.
 *   Open      \______   \ ____   ____ |  | _\_ |__   _______  ___
 *   Source     |       _//  _ \_/ ___\|  |/ /| __ \ /  _ \  \/  /
 *   Jukebox    |    |   (  <_> )  \___|    < | \_\ (  <_> > <  <
 *   Firmware   |____|_  /\____/ \___  >__|_ \|___  /\____/__/\_ \
 *                     \/            \/     \/    \/            \/
 *
 * Copyright (C) 2006 Jonathan Gordon
 *
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License
 * as published by the Free Software Foundation; either version 2
 * of the License, or (at your option) any later version.
 *
 * This software is distributed on an "AS IS" basis, WITHOUT WARRANTY OF ANY
 * KIND, either express or implied.
 *
 ****************************************************************************/
#include "plugin.h"
#include "lib/playback_control.h"


#if defined(DEBUG) || defined(SIMULATOR)
    #define logf(...) rb->debugf(__VA_ARGS__); rb->debugf("\n")
#elif defined(ROCKBOX_HAS_LOGF)
    #define logf rb->logf
#else
    #define logf(...) do { } while(0)
#endif

#define MAX_LINE_LEN 2048


static unsigned char *buffer;
static size_t buffer_size;
static size_t char_count = 0;
static int line_count = 0;
static int last_action_line = 0;
static int last_char_index = 0;
static bool audio_buf = false;

static char temp_line[MAX_LINE_LEN];
static char copy_buffer[MAX_LINE_LEN];
static char filename[MAX_PATH];
static char eol[3];
static bool newfile;
static struct gui_synclist lists;

#define ACTION_INSERT 0
#define ACTION_GET    1
#define ACTION_REMOVE 2
#define ACTION_UPDATE 3
#define ACTION_CONCAT 4

static void cpuboost(int onoff)
{
#ifdef HAVE_ADJUSTABLE_CPU_FREQ
    rb->cpu_boost((onoff == 1) ? true : false);
#else
    (void)onoff;
#endif
}

static char* _do_action(int action, char* str, int line)
{
    if (line < 0 || line > line_count ||
        (action != ACTION_INSERT && line == line_count) ||
        (action == ACTION_CONCAT && line == 0))
        return NULL;
    int len, lennew;
    int i=0,c=0;
    if (line>=last_action_line)
    {
        i = last_action_line;
        c = last_char_index;
    }
    while (i<line && i<line_count)
    {
        c += rb->strlen(&buffer[c])+1;
        i++;
    }
    switch (action)
    {
        case ACTION_INSERT:
            len = rb->strlen(str)+1;
            if ( char_count+ len > buffer_size )
                return NULL;
            rb->memmove(&buffer[c+len],&buffer[c],char_count-c);
            rb->strcpy(&buffer[c],str);
            char_count += len;
            line_count++;
            break;
        case ACTION_GET:
            if (line > line_count)
                return &buffer[0];
            break;
        case ACTION_REMOVE:
            if (line > line_count)
                return NULL;
            len = rb->strlen(&buffer[c])+1;
            rb->memmove(&buffer[c],&buffer[c+len],char_count-c-len);
            char_count -= len;
            line_count--;
            break;
        case ACTION_UPDATE:
            if (line > line_count)
                return NULL;
            len = rb->strlen(&buffer[c])+1;
            lennew = rb->strlen(str)+1;
            if ( char_count+ lennew-len > buffer_size )
                return NULL;
            rb->memmove(&buffer[c+lennew],&buffer[c+len],char_count-c-len);
            rb->strcpy(&buffer[c],str);
            char_count += lennew-len;
            break;
        case ACTION_CONCAT:
            if (line > line_count)
                return NULL;
            rb->memmove(&buffer[c-1],&buffer[c],char_count-c);
            char_count--;
            line_count--;
            break;
        default:
            return NULL;
    }
    last_action_line = i;
    last_char_index = c;
    return &buffer[c];
}

static char* do_action(int action, char* str, int line)
{
    char *r;
    cpuboost(1);
    r = _do_action(action,str,line);
    cpuboost(0);
    return r;
}

static const char* list_get_name_cb(int selected_item, void* data,
                                    char* buf, size_t buf_len)
{
    (void)data;
    char *b = do_action(ACTION_GET, 0, selected_item);
    if (b == NULL || buf_len == 0)
        return NULL;
    /* strlcpy(dst, src, siz) returns strlen(src) */
    if (rb->strlcpy(buf, b, buf_len) >= buf_len)
    {
        if (buf_len >= 5)
            rb->strcpy(&buf[buf_len-5], " ...");
    }
    return buf;
}

static int speak_editor_line(int selected_item, void *data)
{
    (void)data;
    if (!talk_menus_enabled(rb->global_settings) || selected_item < 0 ||
        selected_item >= line_count)
        return 0;

    const char *text = do_action(ACTION_GET, NULL, selected_item);
    if (!text[0])
        return rb->talk_id(VOICE_BLANK, false);
#ifdef HAVE_ESPEAK
    if (rb->global_settings->tts_enabled)
    {
        char chunk[769];
        bool enqueue = false;
        while (*text && talk_menus_enabled(rb->global_settings))
        {
            size_t length = MIN(rb->strlen(text), sizeof(chunk) - 1);
            while (length > 0 && ((unsigned char)text[length] & 0xc0) == 0x80)
                length--;
            if (length == 0)
                return -1;
            rb->memcpy(chunk, text, length);
            chunk[length] = '\0';
            int result = rb->talk_spell(chunk, enqueue);
            if (result < 0)
                return result;
            text += length;
            enqueue = true;
        }
        return 0;
    }
#endif
    return rb->talk_spell(text, false);
}

static int read_editor_line(int descriptor)
{
    int result = rb->read_line(descriptor, temp_line, MAX_LINE_LEN);
    if (result <= 0 || rb->strlen(temp_line) != MAX_LINE_LEN - 1)
        return result;

    off_t position = rb->lseek(descriptor, 0, SEEK_CUR);
    if (position < 0)
        return -1;

    char next;
    ssize_t count = rb->read(descriptor, &next, 1);
    if (count < 0)
        return -1;
    if (count == 0)
        return result;
    if (next == '\n')
        return result + 1;
    if (next == '\r')
    {
        count = rb->read(descriptor, &next, 1);
        if (count < 0)
            return -1;
        if (count > 0 && next == '\n')
            return result + 2;
    }
    if (rb->lseek(descriptor, position, SEEK_SET) < 0)
        return -1;
    return result;
}

static void get_eol_string(char* fn)
{
    int fd;
    char t;

    /* assume LF first */
    rb->strcpy(eol,"\n");

    if (!fn || !fn[0])
        return;
    fd = rb->open(fn,O_RDONLY);
    if (fd<0)
        return;

    while (1)
    {
        if (!rb->read(fd,&t,1) || t == '\n')
        {
            break;
        }
        if (t == '\r')
        {
            if (rb->read(fd,&t,1) && t=='\n')
                rb->strcpy(eol,"\r\n");
            else
                rb->strcpy(eol,"\r");
            break;
        }
    }
    rb->close(fd);
    return;
}

static bool save_changes(int overwrite)
{
    int fd;
    int i;

    if (newfile || !overwrite)
    {
        if(rb->kbd_input(filename,MAX_PATH, NULL) < 0)
        {
            newfile = true;
            return false;
        }
    }

    fd = rb->open(filename,O_WRONLY|O_CREAT|O_TRUNC, 0666);
    if (fd < 0)
    {
        newfile = true;
        rb->splash(HZ*2, "Changes NOT saved");
        return false;
    }

    rb->lcd_clear_display();

    cpuboost(1);
    for (i=0;i<line_count - 1;i++)
    {
        rb->fdprintf(fd,"%s%s", do_action(ACTION_GET, 0, i), eol);
    }
    if (line_count > 0)  /* No EOL for last item */
        rb->fdprintf(fd,"%s", do_action(ACTION_GET, 0, line_count - 1));
    cpuboost(0);

    rb->close(fd);

    if (newfile || !overwrite)
        /* current directory may have changed */
        rb->reload_directory();

    newfile = false;
    return true;
}

static void setup_lists(struct gui_synclist *lists, int sel)
{
    rb->gui_synclist_init(lists,list_get_name_cb,0, false, 1, NULL);
    rb->gui_synclist_set_voice_callback(lists, speak_editor_line);
    rb->gui_synclist_set_nb_items(lists,line_count);
    lists->selected_item = sel;
    rb->gui_synclist_select_item(lists, sel);
    rb->gui_synclist_draw(lists);
    rb->gui_synclist_speak_item(lists);
}

static void refresh_editor_list(int previous_selection, bool speak)
{
    rb->gui_synclist_set_nb_items(&lists, line_count);
    if (line_count > 0 && line_count <= previous_selection)
        rb->gui_synclist_select_item(&lists, line_count - 1);
    if (speak && previous_selection == rb->gui_synclist_get_sel_pos(&lists))
        rb->gui_synclist_speak_item(&lists);
}

enum {
    MENU_RET_SAVE = -1,
    MENU_RET_NO_UPDATE,
    MENU_RET_UPDATE,
};
static int do_item_menu(int cur_sel)
{
    int ret = MENU_RET_NO_UPDATE;
    MENUITEM_STRINGLIST(menu, "Line Options", NULL,
                        "Find",
                        "Cut/Delete", "Copy",
                        "Insert Above", "Insert Below",
                        "Concat To Above",
                        "Save", "Playback Control");

    switch (rb->do_menu(&menu, NULL, NULL, false))
    {
        case 0: /* find*/
        {
            static char find_str[32] = "";
            if (rb->kbd_input(find_str, sizeof(find_str), NULL) != 0)
                break;

            unsigned long last_tick;
            int i = rb->gui_synclist_get_sel_pos(&lists) + 1;
            rb->gui_synclist_draw(&lists);

            rb->splash_progress_set_delay(HZ / 2); /* wait 1/2 sec before progress */
            last_tick = *(rb->current_tick) + HZ/4;

            cpuboost(1);

            for(; i < line_count; i++)
            {
                char *t = _do_action(ACTION_GET, 0, i);
                //logf("find '%s' ln %d %s\n", find_str, i, t);

                if (TIME_AFTER(*(rb->current_tick), last_tick + HZ/4))
                {
                    rb->splash_progress(i, line_count - i,
                                    "%s (%s)", rb->str(LANG_SEARCH), rb->str(LANG_OFF_ABORT));
                    if (rb->action_userabort(TIMEOUT_NOBLOCK))
                        break;
                    last_tick = *(rb->current_tick);
                }

                if (rb->strcasestr(t, find_str) != NULL)
                {
                    logf("found '%s' @ ln %d\n'%s'\n", find_str, i, t);
                    break;
                }
            }
            cpuboost(0);
            if (i >= line_count)
                rb->splash(HZ * 2, ID2P(LANG_FAILED));
            else
                rb->gui_synclist_select_item(&lists, i);
            break;
        }
        case 1: /* cut */
            if (!line_count)
                break;
            rb->strlcpy(copy_buffer, do_action(ACTION_GET, 0, cur_sel),
                        MAX_LINE_LEN);
            do_action(ACTION_REMOVE, 0, cur_sel);
            ret = MENU_RET_UPDATE;
        break;
        case 2: /* copy */
            if (!line_count)
                break;
            rb->strlcpy(copy_buffer, do_action(ACTION_GET, 0, cur_sel),
                        MAX_LINE_LEN);
            ret = MENU_RET_NO_UPDATE;
        break;
        case 3: /* insert above */
            if (!rb->kbd_input(copy_buffer,MAX_LINE_LEN, NULL))
            {
                do_action(ACTION_INSERT,copy_buffer,cur_sel);
                copy_buffer[0]='\0';
                ret = MENU_RET_UPDATE;
            }
        break;
        case 4: /* insert below */
            if (!rb->kbd_input(copy_buffer,MAX_LINE_LEN, NULL))
            {
                do_action(ACTION_INSERT,copy_buffer,line_count ? cur_sel+1 : 0);
                copy_buffer[0]='\0';
                ret = MENU_RET_UPDATE;
            }
        break;
        case 5: /* cat to above */
            if (cur_sel>0)
            {
                do_action(ACTION_CONCAT,0,cur_sel);
                ret = MENU_RET_UPDATE;
            }
        break;
        case 6: /* save */
            ret = MENU_RET_SAVE;
        break;
        case 7: /* playback menu */
            if (!audio_buf)
                playback_control(NULL);
            else
                rb->splash(HZ, "Cannot restart playback");
            ret = MENU_RET_NO_UPDATE;
        break;
        default:
            ret = MENU_RET_NO_UPDATE;
        break;
    }
    return ret;
}

#ifdef HAVE_LCD_COLOR

#define hex2dec(c) (((c) >= '0' && ((c) <= '9')) ? (toupper(c)) - '0' : \
                                                   (toupper(c)) - 'A' + 10)

static int my_hex_to_rgb(const char* hex, int* color)
{   int ok = 1;
    int i;
    int red, green, blue;

    if (rb->strlen(hex) == 6) {
        for (i=0; i < 6; i++ ) {
            if (!isxdigit(hex[i])) {
                ok=0;
                break;
            }
        }

        if (ok) {
            red = (hex2dec(hex[0]) << 4) | hex2dec(hex[1]);
            green = (hex2dec(hex[2]) << 4) | hex2dec(hex[3]);
            blue = (hex2dec(hex[4]) << 4) | hex2dec(hex[5]);
            *color = LCD_RGBPACK(red,green,blue);
            return 0;
        }
    }

    return -1;
}
#endif /* HAVE_LCD_COLOR */

/* this is the plugin entry point */
enum plugin_status plugin_start(const void* parameter)
{
    int fd;

    bool exit = false;
    int button;
    bool changed = false;
    int cur_sel=0;
#ifdef HAVE_LCD_COLOR
    bool edit_colors_file = false;
#endif

    copy_buffer[0]='\0';

#if LCD_DEPTH > 1
    rb->lcd_set_backdrop(NULL);
#endif
    buffer = rb->plugin_get_buffer(&buffer_size);


    cpuboost(1);

    if (parameter)
    {
#ifdef HAVE_LCD_COLOR
        char *c = NULL;
#endif
        rb->strlcpy(filename, (char*)parameter, MAX_PATH);
        get_eol_string(filename);
        fd = rb->open(filename,O_RDONLY);
        if (fd<0)
        {
            rb->splashf(HZ*2, "Couldnt open file: %s", filename);
            return PLUGIN_ERROR;
        }
#ifdef HAVE_LCD_COLOR
        c = rb->strrchr(filename, '.');
        if (c && !rb->strcmp(c, ".colours"))
            edit_colors_file = true;
#endif
        if (buffer_size <= (size_t)rb->ffilesize(fd) + 0x400)
        {
            buffer = rb->plugin_get_audio_buffer(&buffer_size);
            audio_buf = true;
        }
        /* read in the file */
        int bytes_read;
        while ((bytes_read = read_editor_line(fd)) > 0)
        {
            if (!do_action(ACTION_INSERT,temp_line,line_count))
            {
                rb->splashf(HZ*2,"Error reading file: %s",(char*)parameter);
                rb->close(fd);
                return PLUGIN_ERROR;
            }
        }
        rb->close(fd);
        if (bytes_read < 0)
        {
            cpuboost(0);
            rb->splash(HZ*2, ID2P(LANG_FILE_ERROR));
            return PLUGIN_ERROR;
        }
        newfile = false;
    }
    else
    {
        rb->strcpy(filename,"/");
        rb->strcpy(eol,"\n");
        newfile = true;
    }


    cpuboost(0);

    /* now dump it in the list */
    setup_lists(&lists,0);
    rb->lcd_update();
    while (!exit)
    {
        bool speak_selection = false;
        rb->gui_synclist_draw(&lists);
        cur_sel = rb->gui_synclist_get_sel_pos(&lists);
        button = rb->get_action(CONTEXT_LIST,
                               lists.scheduled_talk_tick ? HZ/5 + 1 : TIMEOUT_BLOCK);
        if (rb->gui_synclist_do_button(&lists, &button))
            continue;
        switch (button)
        {
            case ACTION_STD_OK:
            {
                speak_selection = true;
                if (line_count)
                    rb->strlcpy(temp_line, do_action(ACTION_GET, 0, cur_sel),
                                MAX_LINE_LEN);
                else
                    temp_line[0] = '\0';
#ifdef HAVE_LCD_COLOR
                if (edit_colors_file && line_count)
                {
                    char *name = temp_line, *value = NULL;
                    char extension[16];
                    int color, old_color;
                    bool temp_changed = false;

                    MENUITEM_STRINGLIST(menu, "Edit What?", NULL,
                                        "Extension", "Colour");

                    rb->settings_parseline(temp_line, &name, &value);
                    rb->strlcpy(extension, name, sizeof(extension));
                    if (value)
                        my_hex_to_rgb(value, &color);
                    else
                        color = 0;

                    switch (rb->do_menu(&menu, NULL, NULL, false))
                    {
                        case 0:
                            temp_changed = !rb->kbd_input(extension, sizeof(extension), NULL);
                            break;
                        case 1:
                            old_color = color;
                            rb->set_color(rb->screens[SCREEN_MAIN], name, &color, -1);
                            temp_changed = (value == NULL) || (color != old_color);
                            break;
                    }

                    if (temp_changed)
                    {
                        rb->snprintf(temp_line, MAX_LINE_LEN, "%s: %02X%02X%02X",
                                     extension, RGB_UNPACK_RED(color),
                                     RGB_UNPACK_GREEN(color),
                                     RGB_UNPACK_BLUE(color));
                        do_action(ACTION_UPDATE, temp_line, cur_sel);
                        changed = true;
                    }
                }
                else
#endif
                if (!rb->kbd_input(temp_line,MAX_LINE_LEN, NULL))
                {
                    if (line_count)
                        do_action(ACTION_UPDATE,temp_line,cur_sel);
                    else
                        do_action(ACTION_INSERT,temp_line,cur_sel);
                    changed = true;
                }
            }
            break;
            case ACTION_STD_CONTEXT:
/* These targets have unintuitive STD_MENU keymaps, so we use context keymap instead;
   We don't need the "delete line" action, since this can be done via the menu. */
#if (CONFIG_KEYPAD != SAMSUNG_YH92X_PAD) && (CONFIG_KEYPAD != SAMSUNG_YH820_PAD)
                if (!line_count) break;
                rb->strlcpy(copy_buffer, do_action(ACTION_GET, 0, cur_sel),
                            MAX_LINE_LEN);
                do_action(ACTION_REMOVE, 0, cur_sel);
                changed = true;
                speak_selection = true;
            break;
            case ACTION_STD_MENU:
#endif
            {
                speak_selection = true;
                rb->gui_synclist_scroll_stop(&lists);
                /* do the item menu */
                switch (do_item_menu(cur_sel))
                {
                    case MENU_RET_SAVE:
                        if(save_changes(1))
                            changed = false;
                    break;
                    case MENU_RET_UPDATE:
                        changed = true;
                    break;
                    case MENU_RET_NO_UPDATE:
                    break;
                }
            }
            break;
            case ACTION_STD_CANCEL:
                if (changed)
                {
                    speak_selection = true;
                    rb->gui_synclist_scroll_stop(&lists);
                    MENUITEM_STRINGLIST(menu, "Text Editor", NULL,
                                        "Return",
                                        "Playback Control", "Save Changes",
                                        "Save As...", "Save and Exit",
                                        "Ignore Changes and Exit");
                    switch (rb->do_menu(&menu, NULL, NULL, false))
                    {
                        case 0:
                        break;
                        case 1:
                            if (!audio_buf)
                                playback_control(NULL);
                            else
                                rb->splash(HZ, "Cannot restart playback");
                        break;
                        case 2: //save to disk
                            if(save_changes(1))
                                changed = 0;
                        break;
                        case 3:
                            if(save_changes(0))
                                changed = 0;
                        break;
                        case 4:
                            if(save_changes(1))
                                exit=1;
                        break;
                        case 5:
                            exit=1;
                        break;
                    }
                }
                else exit=1;
            break;
        }
        refresh_editor_list(cur_sel, speak_selection && !exit);
    }
    return PLUGIN_OK;
}
