/* Modified for Rockbox Accessible; change notice dated 2026-10-21. */
/***************************************************************************
 *             __________               __   ___.
 *   Open      \______   \ ____   ____ |  | _\_ |__   _______  ___
 *   Source     |       _//  _ \_/ ___\|  |/ /| __ \ /  _ \  \/  /
 *   Jukebox    |    |   (  <_> )  \___|    < | \_\ (  <_> > <  <
 *   Firmware   |____|_  /\____/ \___  >__|_ \|___  /\____/__/\_ \
 *                     \/            \/     \/    \/            \/
 *
 * Copyright (C) 2017 Marcin Bukat
 * Copyright (C) 2016 Amaury Pouly
 * Copyright (C) 2019 Roman Stolyarov
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

#include <stdlib.h>
#include <unistd.h>
#include <stdio.h>
#include <string.h>
#include <linux/fb.h>
#include <sys/mman.h>
#include <sys/ioctl.h>
#include <fcntl.h>
#include "lcd.h"
#include "lcd-target.h"
#include "backlight-target.h"
#include "backlight.h"
#ifdef HAVE_SCREEN_CURTAIN
#include "mutex.h"
#endif
#include "sysfs.h"
#include "panic.h"

//#define FB_DOUBLEBUF

static int fd = -1;
static struct fb_var_screeninfo vinfo;
static struct fb_fix_screeninfo finfo;
fb_data *framebuffer = NULL; /* global variable, see lcd-target.h */
#ifdef HAVE_SCREEN_CURTAIN
static struct mutex lcd_curtain_mutex;
#endif

#ifdef FB_DOUBLEBUF
static int fb_plane;
int doublebuf;
#else
#define fb_plane 0
#endif

static void redraw(void)
{
#ifdef FB_DOUBLEBUF
    if (doublebuf) {
        vinfo.yoffset = fb_plane * LCD_HEIGHT;
        fb_plane = !fb_plane;
        vinfo.activate = FB_ACTIVATE_VBL;
    }
#endif

    ioctl(fd, FBIOPAN_DISPLAY, &vinfo);
}

void lcd_init_device(void)
{
#ifdef HAVE_SCREEN_CURTAIN
    mutex_init(&lcd_curtain_mutex);
#endif
    const char * const fb_dev = "/dev/fb0";
    fd = open(fb_dev, O_RDWR | O_CLOEXEC);
    if(fd < 0)
    {
        panicf("Cannot open framebuffer: %s\n", fb_dev);
    }

    /* get fixed information */
    if(ioctl(fd, FBIOGET_FSCREENINFO, &finfo) < 0)
    {
        panicf("Cannot read framebuffer fixed information");
    }

    if (finfo.smem_len < FRAMEBUFFER_SIZE)
        panicf("FRAMEBUFFER_SIZE too large for hardware? (%u vs %u)", FRAMEBUFFER_SIZE, finfo.smem_len);
#ifdef FB_DOUBLEBUF
    if (finfo.smem_len >= 2*FRAMEBUFFER_SIZE)
        doublebuf = 1;
    fb_plane = 0;
#endif

    /* get variable information */
    if(ioctl(fd, FBIOGET_VSCREENINFO, &vinfo) < 0)
    {
        panicf("Cannot read framebuffer variable information");
    }

#ifdef FB_DOUBLEBUF
    if (doublebuf) {
        vinfo.yres_virtual = vinfo.yres * 2;
        if(ioctl(fd, FBIOPUT_VSCREENINFO, &vinfo) < 0) {
            panicf("Cannot write framebuffer variable information");
        }
    }

#if 0
    /* check resolution and framebuffer size */
    if(vinfo.xres != LCD_WIDTH || vinfo.yres != LCD_HEIGHT || vinfo.bits_per_pixel != LCD_DEPTH)
    {
        panicf("Unexpected framebuffer resolution: %dx%dx%d\n", vinfo.xres,
            vinfo.yres, vinfo.bits_per_pixel);
    }
#endif
#elif defined(FB_STRIDE_MISMATCH)
    /* For framebuffers wider than the panel and cannot be resized */
    if (vinfo.bits_per_pixel != LCD_DEPTH)
        panicf("Unexpected framebuffer depth: %d", vinfo.bits_per_pixel);
#else
    /* Make sure we match our desired bitdepth */
    if (vinfo.bits_per_pixel != LCD_DEPTH || vinfo.xres != LCD_WIDTH || vinfo.yres != LCD_HEIGHT) {
        vinfo.bits_per_pixel = LCD_DEPTH;
        vinfo.xres = LCD_WIDTH;
        vinfo.yres = LCD_HEIGHT;
        if (ioctl(fd, FBIOPUT_VSCREENINFO, &vinfo)) {
            panicf("Cannot set framebuffer to %dx%dx%d",
               vinfo.xres, vinfo.yres, vinfo.bits_per_pixel);
        }
    }
#endif

    /* map framebuffer */
    framebuffer = mmap(NULL, finfo.smem_len, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if((void *)framebuffer == MAP_FAILED)
    {
        panicf("Cannot map framebuffer");
    }

    memset(framebuffer, 0, finfo.smem_len);

#ifdef HAVE_LCD_ENABLE
    lcd_set_active(true);
#endif
}

#ifdef HAVE_LCD_SHUTDOWN
void lcd_shutdown(void)
{
#ifdef HAVE_SCREEN_CURTAIN
    mutex_lock(&lcd_curtain_mutex);
#endif
    if (fd < 0)
    {
#ifdef HAVE_SCREEN_CURTAIN
        mutex_unlock(&lcd_curtain_mutex);
#endif
        return;
    }
    munmap(framebuffer, finfo.smem_len);
    framebuffer = NULL;
    close(fd);
    fd = -1;
#ifdef HAVE_SCREEN_CURTAIN
    mutex_unlock(&lcd_curtain_mutex);
#endif
}
#endif

#ifdef HAVE_LCD_ENABLE
void lcd_enable(bool on)
{
#ifdef HAVE_SCREEN_CURTAIN
    mutex_lock(&lcd_curtain_mutex);
    if (fd < 0 || lcd_active() == on)
    {
        mutex_unlock(&lcd_curtain_mutex);
        return;
    }

    lcd_set_active(on);
    if (on)
        ioctl(fd, FB_BLANK_UNBLANK);
    else
    {
        memset(framebuffer, 0, finfo.smem_len);
        redraw();
        ioctl(fd, FB_BLANK_POWERDOWN);
    }
    mutex_unlock(&lcd_curtain_mutex);

    if (on)
        send_event(LCD_EVENT_ACTIVATION, NULL);
#else
    if (fd < 0) return;

    if (lcd_active() == on)
        return;

    lcd_set_active(on);

    if (on) {
        send_event(LCD_EVENT_ACTIVATION, NULL);
        ioctl(fd, FB_BLANK_UNBLANK);
    } else {
        memset(framebuffer, 0, finfo.smem_len);
        redraw();
        ioctl(fd, FB_BLANK_POWERDOWN);
    }
#endif
}
#endif

extern void lcd_copy_buffer_rect(fb_data *dst, const fb_data *src,
                                 int width, int height);

#ifdef FB_STRIDE_MISMATCH
/* lcd_copy_buffer_rect() for framebuffers wider than the panel */
static void fb_copy_rect(fb_data *dst, const fb_data *src,
                         int width, int height)
{
    while (height--)
    {
        memcpy(dst, src, width * sizeof(fb_data));
        dst += FB_STRIDE_MISMATCH;
        src += LCD_WIDTH;
    }
}
#endif

#ifdef HAVE_SCREEN_CURTAIN
static void lcd_update_locked(void)
#else
void lcd_update(void)
#endif
{
    if (fd < 0) return;

#ifdef HAVE_SCREEN_CURTAIN
    if (backlight_screen_curtain_active())
    {
        memset(framebuffer, 0, finfo.smem_len);
        redraw();
        return;
    }
#endif
#ifdef HAVE_LCD_ENABLE
    if (lcd_active())
#endif
    {
        /* Copy the Rockbox framebuffer to the second framebuffer */
#ifdef FB_STRIDE_MISMATCH
        /* Strides differ - not one contiguous run */
        fb_copy_rect(LCD_FRAMEBUF_ADDR(0, 0), FBADDR(0, 0),
                     LCD_WIDTH, LCD_HEIGHT);
#else
        fb_data *dst = LCD_FRAMEBUF_ADDR(0, 0) + (fb_plane * FRAMEBUFFER_SIZE);
        lcd_copy_buffer_rect(dst, FBADDR(0,0),
                             LCD_WIDTH*LCD_HEIGHT, 1);
#endif
        redraw();
    }
}

#ifdef HAVE_SCREEN_CURTAIN
static void lcd_update_rect_locked(int x, int y, int width, int height)
#else
void lcd_update_rect(int x, int y, int width, int height)
#endif
{
    if (fd < 0) return;

#ifdef HAVE_SCREEN_CURTAIN
    if (backlight_screen_curtain_active())
    {
        lcd_update_locked();
        return;
    }
#endif
#ifdef HAVE_LCD_ENABLE
    if (lcd_active())
#endif
    {
#ifdef FB_STRIDE_MISMATCH
        /* Strides differ - do line-by-line */
        fb_copy_rect(LCD_FRAMEBUF_ADDR(x, y), FBADDR(x, y), width, height);
#else
        fb_data *dst = LCD_FRAMEBUF_ADDR(x, y) + (fb_plane * FRAMEBUFFER_SIZE);
        fb_data *src = FBADDR(x,y);

        /* Copy part of the Rockbox framebuffer to the second framebuffer */
        if (width < LCD_WIDTH)
        {
            /* Not full width - do line-by-line */
            lcd_copy_buffer_rect(dst, src, width, height);
        }
        else
        {
            /* Full width - copy as one line */
            lcd_copy_buffer_rect(dst, src, LCD_WIDTH*height, 1);
        }
#endif
        redraw();
    }
}

#ifdef HAVE_SCREEN_CURTAIN
void lcd_update(void)
{
    mutex_lock(&lcd_curtain_mutex);
    lcd_update_locked();
    mutex_unlock(&lcd_curtain_mutex);
}

void lcd_update_rect(int x, int y, int width, int height)
{
    mutex_lock(&lcd_curtain_mutex);
    lcd_update_rect_locked(x, y, width, height);
    mutex_unlock(&lcd_curtain_mutex);
}

void lcd_set_screen_curtain(bool enabled)
{
    (void)enabled;
    lcd_update();
}
#endif
