#ifndef SCREEN_CURTAIN_FIXTURE_H
#define SCREEN_CURTAIN_FIXTURE_H

#define _GNU_SOURCE
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <pthread.h>

#define __CONFIG_H__
#define _SKIN_ENGINE_H
#define __UISDL_H__
#define __BUTTON_SDL_H__
#ifndef CURTAIN_NO_ESPEAK
#define HAVE_ESPEAK
#endif
#ifndef CURTAIN_UNSUPPORTED
#define HIBY_R1
#endif
#ifndef CURTAIN_NO_BACKLIGHT
#define HAVE_BACKLIGHT
#endif
#include "config.h"
#define HAVE_BACKLIGHT_BRIGHTNESS
#define HAVE_LCD_ENABLE
#define HAVE_LCD_SLEEP
#define HAVE_LCD_SLEEP_SETTING
#define HAVE_LCD_SHUTDOWN
#define HAVE_EXTENDED_MESSAGING_AND_NAME
#define BACKLIGHT_DRIVER_CLOSE
#define BACKLIGHT_HIBY
#define BACKLIGHT_NO_FADING 0
#define BACKLIGHT_FADING_SW_SETTING 1
#define BACKLIGHT_FADING_SW_HW_REG 2
#define BACKLIGHT_FADING_PWM 4
#ifndef CONFIG_BACKLIGHT_FADING
#define CONFIG_BACKLIGHT_FADING BACKLIGHT_NO_FADING
#endif
#define DEFAULT_BRIGHTNESS_SETTING 80
#define MIN_BRIGHTNESS_SETTING 1
#define MAX_BRIGHTNESS_SETTING 100
#define BRIGHTNESS_STEP 5
#define HZ 100
#define DEFAULT_STACK_SIZE 8192
#define SHAREDBSS_ATTR
#define INIT_ATTR
#define IF_PRIO(...)
#define IF_COP(...)
#define CONFIG_CHARGING 1
#define UNLIKELY(value) (value)
#define LIKELY(value) (value)
#define MIN(first, second) ((first) < (second) ? (first) : (second))
#define MAX(first, second) ((first) > (second) ? (first) : (second))
#define LCD_WIDTH 48
#define LCD_HEIGHT 80
#define LCD_DEPTH 16
#define RGB565 1
#define RGB565SWAPPED 2
#define LCD_PIXELFORMAT RGB565
#define HORIZONTAL_STRIDE 0
#define LCD_STRIDEFORMAT HORIZONTAL_STRIDE
#define LCD_FBWIDTH LCD_WIDTH
#define LCD_FBHEIGHT LCD_HEIGHT
#define LCD_SPLIT_LINES 0
#define SIM_LCD_WIDTH LCD_WIDTH
#define SIM_LCD_HEIGHT LCD_HEIGHT
#define UI_LCD_POSX 7
#define UI_LCD_POSY 9
#define LCD_EVENT_ACTIVATION 1
#define FRAMEBUFFER_SIZE ((unsigned int)(LCD_WIDTH * LCD_HEIGHT * sizeof(fb_data)))

typedef uint16_t fb_data;
extern fb_data application_pixels[LCD_WIDTH * LCD_HEIGHT];
extern bool background;
#define FBADDR(column, row) (application_pixels + (row) * LCD_WIDTH + (column))
extern fb_data *framebuffer;
#ifdef FB_STRIDE_MISMATCH
#define FB_STRIDE_XOFFSET 3
#define LCD_FRAMEBUF_ADDR(column, row) \
    (framebuffer + (row) * FB_STRIDE_MISMATCH + (column) + FB_STRIDE_XOFFSET)
#else
#define LCD_FRAMEBUF_ADDR(column, row) (framebuffer + (row) * LCD_WIDTH + (column))
#endif

enum {
    SYS_TIMEOUT = -1, SYS_USB_CONNECTED = -2, SYS_USB_CONNECTED_ACK = -3,
    SYS_POWEROFF = -4, SYS_REBOOT = -5,
    SYS_CHARGER_CONNECTED = -6, SYS_CHARGER_DISCONNECTED = -7
};
struct queue_event { long id; intptr_t data; };
struct fixture_sender { bool complete; pthread_cond_t condition; };
struct fixture_message { struct queue_event event; struct fixture_sender *sender; };
struct event_queue {
    pthread_mutex_t mutex;
    pthread_cond_t condition;
    struct fixture_message events[512];
    unsigned int read, write;
    struct fixture_sender *current;
};
struct queue_sender_list { bool enabled; };
struct mutex { pthread_mutex_t native; };
extern struct { bool show_shutdown_message; } global_settings;

void queue_init(struct event_queue *queue, bool registered);
void queue_post(struct event_queue *queue, long id, intptr_t data);
intptr_t queue_send(struct event_queue *queue, long id, intptr_t data);
void queue_reply(struct event_queue *queue, intptr_t result);
void queue_wait_w_tmo(struct event_queue *queue, struct queue_event *event, int ticks);
bool queue_empty(const struct event_queue *queue);
void queue_remove_from_head(struct event_queue *queue, long id);
void queue_enable_queue_send(struct event_queue *queue, struct queue_sender_list *senders,
                             unsigned int owner);
unsigned int create_thread(void (*entry)(void), void *stack, size_t size, unsigned int flags,
                            const char *name);
void thread_wait(unsigned int thread);
void mutex_init(struct mutex *mutex);
void mutex_lock(struct mutex *mutex);
void mutex_unlock(struct mutex *mutex);
bool is_keys_locked(void);
bool power_input_present(void);
bool backlight_hw_init(void);
void backlight_hw_on(void);
void backlight_hw_off(void);
void backlight_hw_brightness(int brightness);
void usb_acknowledge(long id, intptr_t data);
void lcd_init_device(void);
void lcd_update(void);
void lcd_update_rect(int column, int row, int width, int height);
void lcd_enable(bool enabled);
void lcd_set_active(bool enabled);
bool lcd_active(void);
void lcd_sleep(void);
void lcd_awake(void);
void lcd_shutdown(void);
void send_event(int id, void *data);
void lcd_copy_buffer_rect(fb_data *destination, const fb_data *source, int width, int height);
bool sysfs_set_int(const char *path, int value);
int hiby_get_outputs(void);
void panicf(const char *format, ...) __attribute__((noreturn, format(printf, 1, 2)));

#endif
