#include "screen_curtain_fixture.h"
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sched.h>
#include <linux/input.h>
#include "../../firmware/export/backlight.h"

fb_data application_pixels[LCD_WIDTH * LCD_HEIGHT];
static pthread_t backlight_worker;
static void (*worker_entry)(void);
static bool panel_active;
static bool plugged;
static int hardware_brightness;
static int hardware_blank;
static unsigned int forbidden_blank_writes;
static unsigned int forbidden_brightness_writes;
static unsigned int usb_acknowledgements;
static bool enforce_curtain;
static bool refresh_stop;
static bool privacy_ready;
static bool wake_touch_enabled;
static unsigned int checked_refreshes;
static unsigned int synchronous_requests;
static unsigned int explicit_replies;
static unsigned int automatic_replies;
#ifndef SIMULATOR
static unsigned int framebuffer_unmaps;
static unsigned int framebuffer_closes;
#endif

#ifdef SIMULATOR
#include <SDL.h>
#include "../../firmware/target/hosted/sdl/lcd-bitmap.c"
#include "../../firmware/target/hosted/sdl/lcd-sdl.c"
#include "../../uisimulator/common/backlight-sim.c"
SDL_Surface *sim_lcd_surface;
SDL_Texture *gui_texture;
SDL_mutex *window_mutex;
bool background = true;
static SDL_Window *fixture_window;
static SDL_Renderer *fixture_renderer;
static const int fixture_width = UI_LCD_POSX + LCD_WIDTH + 11;
static const int fixture_height = UI_LCD_POSY + LCD_HEIGHT + 13;

int __real_SDL_UpdateTexture(SDL_Texture *texture, const SDL_Rect *rectangle,
                             const void *pixels, int pitch);
int __wrap_SDL_UpdateTexture(SDL_Texture *texture, const SDL_Rect *rectangle,
                             const void *pixels, int pitch)
{
    if (__atomic_load_n(&privacy_ready, __ATOMIC_ACQUIRE))
    {
        assert(rectangle);
        for (int row = 0; row < rectangle->h; ++row)
            for (int column = 0; column < rectangle->w; ++column)
                assert(*(const fb_data *)((const char *)pixels + row * pitch + column * 2) == 0);
        ++checked_refreshes;
    }
    return __real_SDL_UpdateTexture(texture, rectangle, pixels, pitch);
}

void sdl_window_render(void)
{
    assert(SDL_RenderCopy(fixture_renderer, gui_texture, NULL, NULL) == 0);
    SDL_RenderPresent(fixture_renderer);
}

bool sdl_window_adjust(void) { return false; }
void lcd_enable(bool enabled) { panel_active = enabled; }
void lcd_sleep(void) { panel_active = false; }
void lcd_awake(void) { panel_active = true; }
void lcd_shutdown(void) {}
#else
#include <linux/fb.h>
#include <sys/mman.h>
#include "../../firmware/target/hosted/lcd-linuxfb.c"
#include "../../firmware/target/hosted/backlight-unix.c"
static unsigned char mapped_pixels[FRAMEBUFFER_SIZE * 3];

int __wrap_open(const char *path, int flags, ...)
{
    (void)flags;
    assert(strcmp(path, "/dev/fb0") == 0);
    return 123;
}

int __wrap_close(int handle) { assert(handle == 123); ++framebuffer_closes; return 0; }

int __wrap_ioctl(int handle, unsigned long request, ...)
{
    assert(handle == 123);
    va_list arguments;
    va_start(arguments, request);
    if (request == FBIOGET_FSCREENINFO)
    {
        struct fb_fix_screeninfo *fixed = va_arg(arguments, void *);
        memset(fixed, 0, sizeof(*fixed));
        fixed->smem_len = sizeof(mapped_pixels);
    }
    else if (request == FBIOGET_VSCREENINFO)
    {
        struct fb_var_screeninfo *variable = va_arg(arguments, void *);
        memset(variable, 0, sizeof(*variable));
        variable->xres = LCD_WIDTH;
        variable->yres = LCD_HEIGHT;
        variable->bits_per_pixel = LCD_DEPTH;
    }
    else if (request == FBIOPAN_DISPLAY &&
             __atomic_load_n(&privacy_ready, __ATOMIC_ACQUIRE))
    {
        for (size_t index = 0; index < sizeof(mapped_pixels); ++index)
            assert(mapped_pixels[index] == 0);
        ++checked_refreshes;
    }
    va_end(arguments);
    return 0;
}

void *__wrap_mmap(void *address, size_t length, int protection, int flags,
                  int handle, off_t offset)
{
    (void)address; (void)protection; (void)flags; (void)offset;
    assert(handle == 123 && length == sizeof(mapped_pixels));
    return mapped_pixels;
}

int __wrap_munmap(void *address, size_t length)
{
    assert(address == mapped_pixels && length == sizeof(mapped_pixels));
    ++framebuffer_unmaps;
    return 0;
}
#endif

#include "../../firmware/backlight.c"
#if CONFIG_BACKLIGHT_FADING == BACKLIGHT_FADING_SW_SETTING
#include "../../firmware/backlight-sw-fading.c"
#endif
#include "../../firmware/target/hosted/hiby/r1/button-r1.c"

typeof(global_settings) global_settings = { true };

bool touchscreen_wake_enabled(void)
{
    return wake_touch_enabled;
}

void panicf(const char *format, ...)
{
    va_list arguments;
    va_start(arguments, format);
    vfprintf(stderr, format, arguments);
    va_end(arguments);
    abort();
}

void mutex_init(struct mutex *mutex)
{
    pthread_mutexattr_t attributes;
    assert(pthread_mutexattr_init(&attributes) == 0);
    assert(pthread_mutexattr_settype(&attributes, PTHREAD_MUTEX_RECURSIVE) == 0);
    assert(pthread_mutex_init(&mutex->native, &attributes) == 0);
    assert(pthread_mutexattr_destroy(&attributes) == 0);
}
void mutex_lock(struct mutex *mutex) { assert(pthread_mutex_lock(&mutex->native) == 0); }
void mutex_unlock(struct mutex *mutex) { assert(pthread_mutex_unlock(&mutex->native) == 0); }

void queue_init(struct event_queue *queue, bool registered)
{
    (void)registered;
    assert(pthread_mutex_init(&queue->mutex, NULL) == 0);
    assert(pthread_cond_init(&queue->condition, NULL) == 0);
}

static void enqueue_locked(struct event_queue *queue, long id, intptr_t data,
                            struct fixture_sender *sender)
{
    assert(queue->write - queue->read < 512);
    queue->events[queue->write++ % 512] = (struct fixture_message){{id, data}, sender};
    assert(pthread_cond_signal(&queue->condition) == 0);
}

void queue_post(struct event_queue *queue, long id, intptr_t data)
{
    assert(pthread_mutex_lock(&queue->mutex) == 0);
    enqueue_locked(queue, id, data, NULL);
    assert(pthread_mutex_unlock(&queue->mutex) == 0);
}

intptr_t queue_send(struct event_queue *queue, long id, intptr_t data)
{
    struct fixture_sender sender = {false, PTHREAD_COND_INITIALIZER};
    assert(pthread_mutex_lock(&queue->mutex) == 0);
    ++synchronous_requests;
    enqueue_locked(queue, id, data, &sender);
    while (!sender.complete)
        assert(pthread_cond_wait(&sender.condition, &queue->mutex) == 0);
    assert(pthread_mutex_unlock(&queue->mutex) == 0);
    assert(pthread_cond_destroy(&sender.condition) == 0);
    return 0;
}

static void reply_locked(struct event_queue *queue)
{
    if (queue->current)
    {
        queue->current->complete = true;
        assert(pthread_cond_signal(&queue->current->condition) == 0);
        queue->current = NULL;
    }
}

void queue_reply(struct event_queue *queue, intptr_t result)
{
    (void)result;
    assert(pthread_mutex_lock(&queue->mutex) == 0);
    if (queue->current)
        ++explicit_replies;
    reply_locked(queue);
    assert(pthread_mutex_unlock(&queue->mutex) == 0);
}

void queue_wait_w_tmo(struct event_queue *queue, struct queue_event *event, int ticks)
{
    (void)ticks;
    assert(pthread_mutex_lock(&queue->mutex) == 0);
    if (queue->current)
        ++automatic_replies;
    reply_locked(queue);
    while (queue->read == queue->write)
        assert(pthread_cond_wait(&queue->condition, &queue->mutex) == 0);
    struct fixture_message message = queue->events[queue->read++ % 512];
    *event = message.event;
    queue->current = message.sender;
    assert(pthread_mutex_unlock(&queue->mutex) == 0);
}

bool queue_empty(const struct event_queue *queue)
{
    struct event_queue *mutable = (struct event_queue *)queue;
    assert(pthread_mutex_lock(&mutable->mutex) == 0);
    bool empty = queue->read == queue->write;
    assert(pthread_mutex_unlock(&mutable->mutex) == 0);
    return empty;
}

void queue_remove_from_head(struct event_queue *queue, long id)
{
    assert(pthread_mutex_lock(&queue->mutex) == 0);
    while (queue->read != queue->write &&
           queue->events[queue->read % 512].event.id == id)
        ++queue->read;
    assert(pthread_mutex_unlock(&queue->mutex) == 0);
}

void queue_enable_queue_send(struct event_queue *queue, struct queue_sender_list *senders,
                             unsigned int owner)
{
    (void)queue;
    assert(owner == 1);
    senders->enabled = true;
}

static void *run_backlight(void *argument) { (void)argument; worker_entry(); return NULL; }
unsigned int create_thread(void (*entry)(void), void *stack, size_t size, unsigned int flags,
                            const char *name)
{
    (void)stack; (void)size; (void)flags; (void)name;
    worker_entry = entry;
    assert(pthread_create(&backlight_worker, NULL, run_backlight, NULL) == 0);
    return 1;
}
void thread_wait(unsigned int thread) { assert(thread == 1); assert(pthread_join(backlight_worker, NULL) == 0); }
bool is_keys_locked(void) { return false; }
bool power_input_present(void) { return plugged; }
bool lcd_active(void) { return panel_active; }
void lcd_set_active(bool enabled) { panel_active = enabled; }
void send_event(int id, void *data) { (void)id; (void)data; lcd_update(); }
int hiby_get_outputs(void) { return 2; }
void usb_acknowledge(long id, intptr_t data)
{
    assert(id == SYS_USB_CONNECTED_ACK && data == 42);
    ++usb_acknowledgements;
}

bool sysfs_set_int(const char *path, int value)
{
    if (strstr(path, "/blank"))
    {
        hardware_blank = value;
        if (enforce_curtain && value != 0)
            ++forbidden_blank_writes;
    }
    else
    {
        assert(strstr(path, "/brightness"));
        hardware_brightness = value;
        if (enforce_curtain && value != MIN_BRIGHTNESS_SETTING)
            ++forbidden_brightness_writes;
    }
    return true;
}

void lcd_copy_buffer_rect(fb_data *destination, const fb_data *source, int width, int height)
{
    while (height--)
    {
        memcpy(destination, source, width * sizeof(*source));
        destination += LCD_WIDTH;
        source += LCD_WIDTH;
    }
}

static void flush_backlight(void)
{
    backlight_set_screen_curtain(backlight_screen_curtain_active());
}

static void timeout_ticks(unsigned int count)
{
    for (unsigned int index = 0; index < count; ++index)
        queue_post(&backlight_queue, SYS_TIMEOUT, 0);
    flush_backlight();
}

static void assert_black(void)
{
#ifdef SIMULATOR
    SDL_Surface *capture = SDL_CreateRGBSurface(0, fixture_width, fixture_height, 32,
                                               0x00ff0000, 0x0000ff00, 0x000000ff, 0);
    assert(capture);
    assert(SDL_RenderReadPixels(fixture_renderer, NULL, capture->format->format,
                                capture->pixels, capture->pitch) == 0);
    for (int row = 0; row < fixture_height; ++row)
        for (int column = 0; column < fixture_width; ++column)
        {
            Uint32 pixel = *(Uint32 *)((char *)capture->pixels + row * capture->pitch + column * 4);
            bool on_lcd = column >= UI_LCD_POSX && column < UI_LCD_POSX + LCD_WIDTH &&
                          row >= UI_LCD_POSY && row < UI_LCD_POSY + LCD_HEIGHT;
            assert((pixel & 0x00ffffff) == (on_lcd ? 0 : 0xff00ff));
        }
    SDL_FreeSurface(capture);
#else
    for (size_t index = 0; index < sizeof(mapped_pixels); ++index)
        assert(mapped_pixels[index] == 0);
#endif
    for (size_t index = 0; index < LCD_WIDTH * LCD_HEIGHT; ++index)
        assert(application_pixels[index] == 0xffff);
}

static void *refresh_worker(void *argument)
{
    (void)argument;
    while (!__atomic_load_n(&refresh_stop, __ATOMIC_ACQUIRE))
    {
        lcd_update();
        lcd_update_rect(1, 2, 13, 7);
        sched_yield();
    }
    return NULL;
}

static void *toggle_worker(void *argument)
{
    uintptr_t identity = (uintptr_t)argument;
    for (unsigned int index = 0; index < 40; ++index)
        backlight_set_screen_curtain(((index + identity) & 1) != 0);
    return NULL;
}

static void initialize_output(void)
{
#ifdef SIMULATOR
    assert(SDL_Init(SDL_INIT_VIDEO) == 0);
    fixture_window = SDL_CreateWindow("curtain fixture", SDL_WINDOWPOS_UNDEFINED,
        SDL_WINDOWPOS_UNDEFINED, fixture_width, fixture_height, SDL_WINDOW_HIDDEN);
    assert(fixture_window);
    fixture_renderer = SDL_CreateRenderer(fixture_window, -1, SDL_RENDERER_SOFTWARE);
    assert(fixture_renderer);
    window_mutex = SDL_CreateMutex();
    assert(window_mutex);
    gui_texture = SDL_CreateTexture(fixture_renderer, SDL_PIXELFORMAT_RGB565,
        SDL_TEXTUREACCESS_STREAMING, fixture_width, fixture_height);
    assert(gui_texture);
    SDL_Surface *skin = SDL_CreateRGBSurface(0, fixture_width, fixture_height, 16, 0, 0, 0, 0);
    assert(skin);
    SDL_FillRect(skin, NULL, SDL_MapRGB(skin->format, 255, 0, 255));
    assert(SDL_UpdateTexture(gui_texture, NULL, skin->pixels, skin->pitch) == 0);
    SDL_FreeSurface(skin);
    sim_lcd_surface = SDL_CreateRGBSurface(0, LCD_WIDTH, LCD_HEIGHT, 16, 0, 0, 0, 0);
    assert(sim_lcd_surface);
#endif
    lcd_init_device();
    for (size_t index = 0; index < LCD_WIDTH * LCD_HEIGHT; ++index)
        application_pixels[index] = 0xffff;
    backlight_init();
    backlight_set_timeout(7);
    backlight_set_timeout_plugged(11);
    backlight_set_brightness(65);
#if CONFIG_BACKLIGHT_FADING == BACKLIGHT_FADING_SW_SETTING
    backlight_set_fade_in(false);
    backlight_set_fade_out(false);
#endif
    flush_backlight();
    lcd_update();
}

int main(int argument_count, char **arguments)
{
    assert(argument_count == 2);
    initialize_output();
    assert(!backlight_screen_curtain_active());
    assert(button_map(BTN_TOUCH) == BUTTON_TOUCH);
    backlight_off();
    flush_backlight();
    assert(button_map(BTN_TOUCH) == 0);
    wake_touch_enabled = true;
    assert(button_map(BTN_TOUCH) == BUTTON_TOUCH);
    wake_touch_enabled = false;
    assert(button_map(BTN_TOUCH) == 0);
    timeout_ticks(20);
    assert(!lcd_active());

#if CONFIG_BACKLIGHT_FADING == BACKLIGHT_FADING_SW_SETTING
    backlight_set_fade_in(true);
    backlight_on();
    flush_backlight();
    assert(backlight_fading_state == FADING_UP);
#endif
    backlight_set_screen_curtain(true);
    __atomic_store_n(&privacy_ready, true, __ATOMIC_RELEASE);
#if CONFIG_BACKLIGHT_FADING == BACKLIGHT_FADING_SW_SETTING
    assert(backlight_fading_state == NOT_FADING);
#endif
    assert(backlight_screen_curtain_active());
    assert(lcd_active());
    assert(is_backlight_on(true));
    assert(button_map(BTN_TOUCH) == BUTTON_TOUCH);
    assert(button_map(KEY_POWER) == BUTTON_POWER);
    assert(button_map(KEY_NEXTSONG) == BUTTON_NEXT);
    assert(button_map(KEY_PLAYPAUSE) == BUTTON_PLAY);
    assert_black();
    enforce_curtain = true;

    for (unsigned int index = 0; index < 100; ++index)
    {
        backlight_on();
        backlight_off();
        backlight_set_brightness(index % 2 ? 0 : 999);
        queue_post(&backlight_queue, SYS_CHARGER_CONNECTED, 0);
        queue_post(&backlight_queue, SYS_CHARGER_DISCONNECTED, 0);
        queue_post(&backlight_queue, LCD_SLEEP, 0);
        lcd_set_sleep_after_backlight_off(0);
        timeout_ticks(3);
        assert(lcd_active());
        assert(button_map(BTN_TOUCH) == BUTTON_TOUCH);
        lcd_update_rect(2, 3, 11, 9);
        assert_black();
    }
    queue_post(&backlight_queue, SYS_USB_CONNECTED, 42);
    backlight_set_timeout(13);
    backlight_set_timeout_plugged(17);
    backlight_set_brightness(37);
    flush_backlight();
    assert(backlight_brightness == 37);
    assert(backlight_get_current_timeout() == 13 * HZ);
    assert(usb_acknowledgements == 1);
    assert(forbidden_blank_writes == 0);
    assert(forbidden_brightness_writes == 0);
#ifndef SIMULATOR
    assert(hardware_blank == 0 && hardware_brightness == MIN_BRIGHTNESS_SETTING);
#endif

    if (strcmp(arguments[1], "stress") == 0)
    {
        pthread_t refresh;
        assert(pthread_create(&refresh, NULL, refresh_worker, NULL) == 0);
        for (unsigned int index = 0; index < 100; ++index)
        {
            enforce_curtain = false;
            __atomic_store_n(&privacy_ready, false, __ATOMIC_RELEASE);
            backlight_set_screen_curtain(false);
            backlight_set_screen_curtain(true);
            __atomic_store_n(&privacy_ready, true, __ATOMIC_RELEASE);
            enforce_curtain = true;
        }
        __atomic_store_n(&refresh_stop, true, __ATOMIC_RELEASE);
        assert(pthread_join(refresh, NULL) == 0);
        assert_black();
    }

    if (strcmp(arguments[1], "callers") == 0)
    {
        pthread_t callers[4];
        enforce_curtain = false;
        __atomic_store_n(&privacy_ready, false, __ATOMIC_RELEASE);
        for (uintptr_t index = 0; index < 4; ++index)
            assert(pthread_create(&callers[index], NULL, toggle_worker, (void *)index) == 0);
        for (unsigned int index = 0; index < 4; ++index)
            assert(pthread_join(callers[index], NULL) == 0);
        backlight_set_screen_curtain(true);
        __atomic_store_n(&privacy_ready, true, __ATOMIC_RELEASE);
        assert_black();
    }

    enforce_curtain = false;
    __atomic_store_n(&privacy_ready, false, __ATOMIC_RELEASE);
    backlight_set_screen_curtain(false);
    assert(!backlight_screen_curtain_active());
    assert(backlight_brightness == 37);
    assert(backlight_get_current_timeout() == 13 * HZ);
    assert(is_backlight_on(true));
    assert(button_map(BTN_TOUCH) == BUTTON_TOUCH);
#ifndef SIMULATOR
    assert(hardware_brightness == 37);
    assert(*LCD_FRAMEBUF_ADDR(0, 0) == 0xffff);
#else
    uint8_t alpha;
    assert(SDL_GetSurfaceAlphaMod(lcd_surface, &alpha) == 0);
    assert(alpha == 37 * 255 / 100);
    assert(*(fb_data *)lcd_surface->pixels == 0xffff);
#endif
#if CONFIG_BACKLIGHT_FADING == BACKLIGHT_FADING_SW_SETTING
    backlight_set_fade_in(false);
    backlight_set_fade_out(true);
    backlight_off();
    flush_backlight();
    assert(backlight_fading_state == FADING_DOWN);
    timeout_ticks(1);
    backlight_set_screen_curtain(true);
    assert(backlight_fading_state == NOT_FADING);
    __atomic_store_n(&privacy_ready, true, __ATOMIC_RELEASE);
    timeout_ticks(100);
    assert(lcd_active());
    assert_black();
    __atomic_store_n(&privacy_ready, false, __ATOMIC_RELEASE);
    backlight_set_fade_out(false);
    backlight_set_screen_curtain(false);
#endif
    timeout_ticks(13);
    assert(!is_backlight_on(true));
    assert(button_map(BTN_TOUCH) == 0);
    backlight_set_screen_curtain(true);
    backlight_set_timeout(-1);
    flush_backlight();
    backlight_set_screen_curtain(false);
    assert(!is_backlight_on(true));
    backlight_set_screen_curtain(true);
    backlight_set_timeout_plugged(0);
    flush_backlight();
    plugged = true;
    backlight_set_screen_curtain(false);
    assert(backlight_get_current_timeout() == 0 && is_backlight_on(true));
    backlight_set_screen_curtain(true);
    queue_post(&backlight_queue, SYS_POWEROFF, 0);
    flush_backlight();
    assert_black();
    assert(checked_refreshes >= 100);
    assert(explicit_replies == synchronous_requests);
    assert(automatic_replies == 0);
    backlight_close();
    lcd_shutdown();
#ifndef SIMULATOR
    assert(framebuffer_unmaps == 1 && framebuffer_closes == 1);
    assert(framebuffer == NULL && fd == -1);
    lcd_update();
    lcd_update_rect(0, 0, 1, 1);
    lcd_enable(true);
    lcd_shutdown();
    assert(framebuffer_unmaps == 1 && framebuffer_closes == 1);
#endif
    puts("screen curtain source harness passed");
    return 0;
}
