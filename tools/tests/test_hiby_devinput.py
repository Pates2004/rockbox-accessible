"""Exercise real Linux input sampling without physical or global input."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root


ROOT = Path(__file__).resolve().parents[2]
DRIVER = ROOT / 'firmware/target/hosted/button-devinput.c'
HEADERS = {
    'kernel.h': '#include <stdbool.h>\n',
    'sysfs.h': '',
    'panic.h': '',
    'button.h': '''
#include <stdbool.h>
#include <linux/input.h>
#define BUTTON_VOL_UP 0x10
#define BUTTON_VOL_DOWN 0x20
#define BUTTON_POWER 1
#define BUTTON_NEXT 4
#define BUTTON_TOUCH 0x40
#define BUTTON_TOUCHSCREEN 0x2000000
int button_map(int keycode);
int touchscreen_to_pixels(int horizontal, int vertical, int *data);
''',
}
HARNESS = r'''
#include <assert.h>
#include <errno.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <linux/input.h>
#include "button.h"

static struct input_event queued[256];
static size_t queued_count, consumed;
static struct input_event extra_queued[2][256];
static size_t extra_count[2], extra_consumed[2];
static int ready_flags[3], read_errors[3], closed[3];
static int snapshot_buttons[3], snapshot_failed;
static int __attribute__((unused)) snapshot_tracking = -2;
static int poll_error, polls;
static int button_read_device(int *data);
static void touchscreen_enable_device(bool enabled);
static void touchscreen_last_state(int *horizontal, int *vertical, int *state);

int button_map(int keycode)
{
    switch (keycode)
    {
        case KEY_VOLUMEUP: return BUTTON_VOL_UP;
        case KEY_VOLUMEDOWN: return BUTTON_VOL_DOWN;
        case KEY_POWER: return BUTTON_POWER;
        case KEY_NEXTSONG: return BUTTON_NEXT;
        case BTN_TOUCH: return BUTTON_TOUCH;
        default: return 0;
    }
}

int touchscreen_to_pixels(int horizontal, int vertical, int *data)
{
    *data = (horizontal << 16) | vertical;
    return BUTTON_TOUCHSCREEN;
}

static int fixture_poll(struct pollfd *descriptors, nfds_t count, int timeout)
{
    assert(timeout == 0 && count <= 3);
    assert(++polls < 1024);
    int ready = 0;
    for (nfds_t index = 0; index < count; ++index)
        descriptors[index].revents = 0;
    if (poll_error)
    {
        errno = poll_error;
        return -1;
    }
    for (nfds_t index = 0; index < count; ++index)
    {
        size_t available = index ? extra_count[index - 1] - extra_consumed[index - 1] : queued_count - consumed;
        if (descriptors[index].fd >= 0 && (available || ready_flags[index]))
        {
            descriptors[index].revents = ready_flags[index] ? ready_flags[index] : POLLIN;
            ++ready;
        }
    }
    return ready;
}

static ssize_t fixture_read(int descriptor, void *buffer, size_t count)
{
    int index = descriptor - 42;
    assert(index >= 0 && index < 3 && count == sizeof(struct input_event));
    if (read_errors[index])
    {
        errno = read_errors[index] > 0 ? read_errors[index] : 0;
        return read_errors[index] > 0 ? -1 : (read_errors[index] == -1 ? 0 : 3);
    }
    if (index)
    {
        assert(extra_consumed[index - 1] < extra_count[index - 1]);
        memcpy(buffer, &extra_queued[index - 1][extra_consumed[index - 1]++], count);
    }
    else
    {
        assert(consumed < queued_count);
        memcpy(buffer, &queued[consumed++], count);
    }
    return (ssize_t)count;
}

static int fixture_close(int descriptor)
{
    assert(descriptor >= 42 && descriptor < 45);
    ++closed[descriptor - 42];
    return 0;
}

#ifdef HIBY_R1
static int __attribute__((unused)) fixture_ioctl(int descriptor, unsigned long request, void *argument)
{
    int index = descriptor - 42;
    assert(index >= 0 && index < 3);
    if (!snapshot_failed && _IOC_NR(request) == 0x40 + ABS_MT_TRACKING_ID && snapshot_tracking != -2)
    {
        memset(argument, 0, sizeof(struct input_absinfo));
        ((struct input_absinfo *)argument)->value = snapshot_tracking;
        return 0;
    }
    if (snapshot_failed || _IOC_NR(request) != 0x18)
    {
        errno = EIO;
        return -1;
    }
    unsigned long *bits = argument;
    memset(bits, 0, _IOC_SIZE(request));
    for (int code = 0; code <= KEY_MAX; ++code)
        if (button_map(code) & snapshot_buttons[index])
            bits[code / (8 * sizeof(*bits))] |= 1ul << (code % (8 * sizeof(*bits)));
    return 0;
}
#endif

static void enqueue_on(int index, unsigned short type, unsigned short code, int value)
{
    assert(index >= 0 && index < 3);
    if (!index)
    {
        assert(queued_count < sizeof(queued) / sizeof(queued[0]));
        queued[queued_count++] = (struct input_event){ .type = type, .code = code, .value = value };
    }
    else
    {
        assert(extra_count[index - 1] < 256);
        extra_queued[index - 1][extra_count[index - 1]++] =
            (struct input_event){ .type = type, .code = code, .value = value };
    }
}

static void enqueue(unsigned short type, unsigned short code, int value)
{
    enqueue_on(0, type, code, value);
}

static void frame(void)
{
    enqueue(EV_SYN, SYN_REPORT, 0);
}

#define poll fixture_poll
#define read fixture_read
#define close fixture_close
#ifdef HIBY_R1
#define ioctl fixture_ioctl
#endif
#include "driver-under-test.c"
#ifdef HIBY_R1
#undef ioctl
#endif
#undef close
#undef read
#undef poll

static int sample(int *data)
{
    polls = 0;
    return button_read_device(data);
}

static void touch(int horizontal, int vertical, int tracking)
{
    enqueue(EV_ABS, ABS_MT_TRACKING_ID, tracking);
    enqueue(EV_ABS, ABS_MT_POSITION_X, horizontal);
    enqueue(EV_ABS, ABS_MT_POSITION_Y, vertical);
    frame();
}

int main(int count, char **arguments)
{
    assert(count == 2);
    num_devices = 1;
    poll_fds[0] = (struct pollfd){ .fd = 42, .events = POLLIN };
    int data = 0;
    if (!strncmp(arguments[1], "multi-", 6))
    {
        num_devices = 3;
        poll_fds[1] = (struct pollfd){ .fd = 43, .events = POLLIN };
        poll_fds[2] = (struct pollfd){ .fd = 44, .events = POLLIN };
        if (!strcmp(arguments[1], "multi-foreign-syn"))
        {
            enqueue(EV_KEY, KEY_POWER, 1); frame();
            assert(sample(&data) == BUTTON_POWER);
            enqueue(EV_KEY, KEY_POWER, 2); frame();
            enqueue_on(1, EV_ABS, ABS_MT_TRACKING_ID, 1);
            enqueue_on(1, EV_ABS, ABS_MT_POSITION_X, 80);
            enqueue_on(1, EV_ABS, ABS_MT_POSITION_Y, 90);
            enqueue_on(1, EV_SYN, SYN_REPORT, 0);
            assert(sample(&data) == (BUTTON_POWER | BUTTON_TOUCHSCREEN));
            assert(data == ((80 << 16) | 90));
        }
        else if (!strcmp(arguments[1], "multi-key-mid-frame"))
        {
            enqueue_on(1, EV_ABS, ABS_MT_TRACKING_ID, 1);
            enqueue_on(1, EV_ABS, ABS_MT_POSITION_X, 80);
            enqueue_on(1, EV_ABS, ABS_MT_POSITION_Y, 90);
            enqueue_on(1, EV_SYN, SYN_REPORT, 0);
            enqueue_on(2, EV_KEY, KEY_VOLUMEUP, 1);
            assert(sample(&data) == BUTTON_VOL_UP && data == 0);
            assert(sample(&data) == (BUTTON_VOL_UP | BUTTON_TOUCHSCREEN));
            assert(data == ((80 << 16) | 90));
        }
        else if (!strcmp(arguments[1], "multi-owned-keys"))
        {
            enqueue(EV_KEY, KEY_VOLUMEUP, 1);
            assert(sample(&data) == BUTTON_VOL_UP);
            enqueue_on(2, EV_KEY, KEY_VOLUMEUP, 1);
            assert(sample(&data) == BUTTON_VOL_UP);
            enqueue(EV_KEY, KEY_VOLUMEUP, 0);
            assert(sample(&data) == BUTTON_VOL_UP);
            ready_flags[0] = POLLNVAL;
            assert(sample(&data) == BUTTON_VOL_UP && closed[0] == 1);
            enqueue_on(2, EV_KEY, KEY_VOLUMEUP, 0);
            assert(sample(&data) == 0);
        }
        else if (!strcmp(arguments[1], "multi-fairness"))
        {
            for (int press = 0; press < 12; ++press)
                enqueue(EV_KEY, KEY_POWER, !(press % 2));
            enqueue_on(2, EV_KEY, KEY_VOLUMEUP, 1);
            assert(sample(&data) == BUTTON_POWER);
            assert(sample(&data) == (BUTTON_POWER | BUTTON_VOL_UP));
            for (int press = 1; press < 12; ++press)
                assert(sample(&data) == (BUTTON_VOL_UP | (press % 2 ? 0 : BUTTON_POWER)));
            enqueue_on(2, EV_KEY, KEY_VOLUMEUP, 0);
            assert(sample(&data) == 0);
        }
        else if (!strcmp(arguments[1], "multi-drop-isolation"))
        {
            enqueue(EV_KEY, KEY_VOLUMEUP, 1);
            assert(sample(&data) == BUTTON_VOL_UP);
            enqueue_on(2, EV_KEY, KEY_VOLUMEUP, 1);
            assert(sample(&data) == BUTTON_VOL_UP);
            enqueue_on(2, EV_SYN, SYN_DROPPED, 0);
            enqueue_on(2, EV_KEY, KEY_VOLUMEDOWN, 1);
            enqueue_on(2, EV_SYN, SYN_REPORT, 0);
            assert(sample(&data) == BUTTON_VOL_UP);
            enqueue(EV_KEY, KEY_VOLUMEUP, 0);
            assert(sample(&data) == 0);
        }
        else
            assert(false);
    }
    else if (!strcmp(arguments[1], "queued-clicks"))
    {
        enqueue(EV_KEY, KEY_VOLUMEUP, 1); frame();
        enqueue(EV_KEY, KEY_VOLUMEUP, 0); frame();
        enqueue(EV_KEY, KEY_VOLUMEDOWN, 1); frame();
        enqueue(EV_KEY, KEY_VOLUMEDOWN, 0); frame();
        assert(sample(&data) == BUTTON_VOL_UP);
        assert(sample(&data) == 0);
        assert(sample(&data) == BUTTON_VOL_DOWN);
        assert(sample(&data) == 0);
        assert(sample(&data) == 0 && consumed == queued_count);
    }
    else if (!strcmp(arguments[1], "chord-edges"))
    {
        enqueue(EV_KEY, KEY_POWER, 1); frame();
        enqueue(EV_KEY, KEY_VOLUMEUP, 1); frame();
        enqueue(EV_KEY, KEY_VOLUMEUP, 0); frame();
        enqueue(EV_KEY, KEY_POWER, 0); frame();
        assert(sample(&data) == BUTTON_POWER);
        assert(sample(&data) == (BUTTON_POWER | BUTTON_VOL_UP));
        assert(sample(&data) == BUTTON_POWER);
        assert(sample(&data) == 0);
    }
    else if (!strcmp(arguments[1], "queued-touch"))
    {
        touch(10, 20, 1);
        touch(80, 20, 1);
        touch(80, 20, -1);
        assert(sample(&data) == BUTTON_TOUCHSCREEN && data == ((10 << 16) | 20));
        assert(sample(&data) == BUTTON_TOUCHSCREEN && data == ((80 << 16) | 20));
        assert(sample(&data) == 0 && data == ((80 << 16) | 20));
        assert(consumed == queued_count);
    }
    else if (!strcmp(arguments[1], "double-touch"))
    {
        touch(12, 25, 1); touch(12, 25, -1);
        touch(19, 28, 2); touch(19, 28, -1);
        assert(sample(&data) == BUTTON_TOUCHSCREEN);
        assert(sample(&data) == 0);
        assert(sample(&data) == BUTTON_TOUCHSCREEN && data == ((19 << 16) | 28));
        assert(sample(&data) == 0);
    }
    else if (!strcmp(arguments[1], "ev-key-touch"))
    {
        enqueue(EV_ABS, ABS_X, 32); enqueue(EV_ABS, ABS_Y, 48);
        enqueue(EV_KEY, BTN_TOUCH, 1); frame();
        enqueue(EV_KEY, BTN_TOUCH, 0); frame();
        assert(sample(&data) == BUTTON_TOUCHSCREEN && data == ((32 << 16) | 48));
        assert(sample(&data) == 0);
    }
    else if (!strcmp(arguments[1], "hold-repeat"))
    {
        enqueue(EV_KEY, KEY_NEXTSONG, 1); frame();
        assert(sample(&data) == BUTTON_NEXT);
        enqueue(EV_KEY, KEY_NEXTSONG, 2); frame();
        assert(sample(&data) == BUTTON_NEXT);
        assert(sample(&data) == BUTTON_NEXT);
        enqueue(EV_KEY, KEY_NEXTSONG, 0); frame();
        assert(sample(&data) == 0);
    }
    else if (!strcmp(arguments[1], "poll-errors"))
    {
        enqueue(EV_KEY, KEY_POWER, 1); frame();
        assert(sample(&data) == BUTTON_POWER);
        poll_error = EINTR;
        assert(sample(&data) == BUTTON_POWER && polls == 1);
        poll_error = EIO;
        assert(sample(&data) == BUTTON_POWER && polls == 1);
        poll_error = 0;
        enqueue(EV_KEY, KEY_POWER, 0); frame();
        assert(sample(&data) == 0);
    }
    else if (!strcmp(arguments[1], "idle-and-disabled"))
    {
        assert(sample(&data) == 0 && polls == 1);
        touchscreen_enable_device(false);
        touch(1, 2, 1); touch(3, 4, -1);
        assert(sample(&data) == 0 && consumed == queued_count);
        int horizontal, vertical, state;
        touchscreen_last_state(&horizontal, &vertical, &state);
        assert(horizontal == 0 && vertical == 0 && state == TOUCHSCREEN_STATE_UNKNOWN);
    }
    else if (!strcmp(arguments[1], "cancel-held-touch"))
    {
        touch(10, 20, 1);
        assert(sample(&data) == BUTTON_TOUCHSCREEN);
        touchscreen_enable_device(false);
        assert(sample(&data) == 0);
        touchscreen_enable_device(true);
        assert(sample(&data) == 0);
        enqueue(EV_ABS, ABS_MT_POSITION_X, 80); frame();
        assert(sample(&data) == 0);
        touch(80, 20, -1);
        assert(sample(&data) == 0);
        touch(31, 42, 2);
        assert(sample(&data) == BUTTON_TOUCHSCREEN && data == ((31 << 16) | 42));
    }
    else if (!strcmp(arguments[1], "cancel-disabled-key-touch"))
    {
        touchscreen_enable_device(false);
        enqueue(EV_KEY, BTN_TOUCH, 1); frame();
        assert(sample(&data) == 0);
        touchscreen_enable_device(true);
        assert(sample(&data) == 0);
        enqueue(EV_KEY, BTN_TOUCH, 0); frame();
        assert(sample(&data) == 0);
        enqueue(EV_ABS, ABS_X, 7); enqueue(EV_ABS, ABS_Y, 9);
        enqueue(EV_KEY, BTN_TOUCH, 1); frame();
        assert(sample(&data) == BUTTON_TOUCHSCREEN && data == ((7 << 16) | 9));
    }
    else if (!strcmp(arguments[1], "cancel-mid-frame"))
    {
        enqueue(EV_ABS, ABS_MT_TRACKING_ID, 1);
        for (int index = 0; index < 200; ++index)
            enqueue(EV_MSC, MSC_SCAN, 0);
        assert(sample(&data) == 0 && consumed < queued_count);
        touchscreen_enable_device(false);
        touchscreen_enable_device(true);
        enqueue(EV_ABS, ABS_MT_POSITION_X, 7);
        enqueue(EV_ABS, ABS_MT_POSITION_Y, 9); frame();
        while (consumed < queued_count)
            assert(sample(&data) == 0);
        touch(7, 9, -1); assert(sample(&data) == 0);
        touch(7, 9, 2); assert(sample(&data) == BUTTON_TOUCHSCREEN);
    }
    else if (!strcmp(arguments[1], "bounded-backlog"))
    {
        for (int index = 0; index < 200; ++index)
            enqueue(EV_MSC, MSC_SCAN, index);
        assert(sample(&data) == 0 && consumed > 0 && consumed <= 64);
        while (consumed < queued_count)
            assert(sample(&data) == 0 && polls <= 64);
    }
    else if (!strncmp(arguments[1], "retire-", 7))
    {
        enqueue(EV_KEY, KEY_POWER, 1);
        assert(sample(&data) == BUTTON_POWER);
        ready_flags[0] = POLLIN | POLLHUP;
        if (!strcmp(arguments[1], "retire-invalid")) ready_flags[0] = POLLNVAL;
        else if (!strcmp(arguments[1], "retire-eof")) read_errors[0] = -1;
        else if (!strcmp(arguments[1], "retire-short")) read_errors[0] = -2;
        else if (!strcmp(arguments[1], "retire-fatal")) read_errors[0] = EIO;
        else if (!strcmp(arguments[1], "retire-hup-again")) read_errors[0] = EAGAIN;
        else if (!strcmp(arguments[1], "retire-readable"))
        {
            enqueue(EV_KEY, KEY_NEXTSONG, 1);
            assert(sample(&data) == (BUTTON_POWER | BUTTON_NEXT));
            read_errors[0] = -1;
        }
        else assert(false);
        assert(sample(&data) == 0 && closed[0] == 1 && polls <= 2);
        assert(sample(&data) == 0);
    }
    else if (!strcmp(arguments[1], "transient-read"))
    {
        enqueue(EV_KEY, KEY_POWER, 1); assert(sample(&data) == BUTTON_POWER);
        ready_flags[0] = POLLIN;
        read_errors[0] = EAGAIN;
        assert(sample(&data) == BUTTON_POWER && polls <= 64 && !closed[0]);
        read_errors[0] = EINTR;
        assert(sample(&data) == BUTTON_POWER && polls <= 64 && !closed[0]);
        ready_flags[0] = read_errors[0] = 0;
        enqueue(EV_KEY, KEY_POWER, 0); assert(sample(&data) == 0);
    }
    else if (!strcmp(arguments[1], "drop-recovery"))
    {
        enqueue(EV_KEY, KEY_POWER, 1); assert(sample(&data) == BUTTON_POWER);
        enqueue(EV_SYN, SYN_DROPPED, 0);
        enqueue(EV_KEY, KEY_NEXTSONG, 1); frame();
        snapshot_buttons[0] = BUTTON_VOL_UP;
        assert(sample(&data) == BUTTON_VOL_UP);
        enqueue(EV_KEY, KEY_VOLUMEUP, 0); assert(sample(&data) == 0);
    }
    else if (!strcmp(arguments[1], "drop-query-failed"))
    {
        enqueue(EV_KEY, KEY_POWER, 1); assert(sample(&data) == BUTTON_POWER);
        enqueue(EV_SYN, SYN_DROPPED, 0); frame(); snapshot_failed = 1;
        assert(sample(&data) == 0 && !closed[0]);
        enqueue(EV_KEY, KEY_NEXTSONG, 1); assert(sample(&data) == BUTTON_NEXT);
    }
    else if (!strcmp(arguments[1], "drop-touch"))
    {
        touch(12, 34, 1); assert(sample(&data) == BUTTON_TOUCHSCREEN);
        enqueue(EV_SYN, SYN_DROPPED, 0);
        touch(80, 90, -1);
        snapshot_failed = 1;
        assert(sample(&data) == 0);
        enqueue(EV_ABS, ABS_MT_POSITION_X, 80); frame();
        assert(sample(&data) == 0);
        touch(80, 90, -1); assert(sample(&data) == 0);
        touch(80, 90, 2); assert(sample(&data) == BUTTON_TOUCHSCREEN);
    }
    else if (!strcmp(arguments[1], "drop-touch-known-up"))
    {
        touch(12, 34, 1); assert(sample(&data) == BUTTON_TOUCHSCREEN);
        enqueue(EV_SYN, SYN_DROPPED, 0); frame();
        snapshot_tracking = -1;
        assert(sample(&data) == 0);
        touch(80, 90, 2); assert(sample(&data) == BUTTON_TOUCHSCREEN);
    }
    else if (!strcmp(arguments[1], "drop-key-touch-up"))
    {
        enqueue(EV_KEY, BTN_TOUCH, 1); frame();
        assert(sample(&data) == BUTTON_TOUCHSCREEN);
        enqueue(EV_SYN, SYN_DROPPED, 0); frame();
        assert(sample(&data) == 0);
        enqueue(EV_KEY, BTN_TOUCH, 1); frame();
        assert(sample(&data) == BUTTON_TOUCHSCREEN);
    }
    else if (!strcmp(arguments[1], "drop-key-touch-held"))
    {
        enqueue(EV_KEY, BTN_TOUCH, 1); frame();
        assert(sample(&data) == BUTTON_TOUCHSCREEN);
        enqueue(EV_SYN, SYN_DROPPED, 0); frame();
        snapshot_buttons[0] = BUTTON_TOUCH;
        assert(sample(&data) == 0);
        enqueue(EV_ABS, ABS_X, 80); frame();
        assert(sample(&data) == 0);
        enqueue(EV_KEY, BTN_TOUCH, 0); frame(); assert(sample(&data) == 0);
        enqueue(EV_KEY, BTN_TOUCH, 1); frame(); assert(sample(&data) == BUTTON_TOUCHSCREEN);
    }
    else if (!strcmp(arguments[1], "generic-policy"))
    {
        enqueue(EV_KEY, KEY_VOLUMEUP, 1); frame();
        enqueue(EV_KEY, KEY_VOLUMEUP, 0); frame();
        assert(sample(&data) == 0 && consumed == queued_count);
    }
    else
        assert(false);
    puts("PASS real devinput sample");
    return 0;
}
'''
CASES = ('queued-clicks', 'chord-edges', 'queued-touch', 'double-touch',
         'ev-key-touch', 'hold-repeat', 'poll-errors', 'idle-and-disabled',
         'multi-foreign-syn', 'multi-key-mid-frame', 'multi-owned-keys',
         'multi-fairness', 'multi-drop-isolation', 'cancel-held-touch',
         'cancel-disabled-key-touch', 'cancel-mid-frame', 'bounded-backlog',
         'retire-invalid', 'retire-eof', 'retire-short', 'retire-fatal',
         'retire-hup-again', 'retire-readable', 'transient-read',
         'drop-recovery', 'drop-query-failed', 'drop-touch',
         'drop-touch-known-up', 'drop-key-touch-up', 'drop-key-touch-held')


def disable_core_dump():
    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


@unittest.skipUnless(sys.platform == 'linux' and shutil.which('cc'), 'Requires Linux input headers/compiler; run under WSL')
class HibyDevinputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        cls.area = project_materials_root(ROOT) / 'hiby-devinput-tests' / (stamp + '-' + uuid.uuid4().hex[:8])
        cls.area.mkdir(parents=True)
        for name, content in HEADERS.items():
            (cls.area / name).write_text(content, encoding='utf-8')
        cls.production = DRIVER.read_text(encoding='utf-8')
        cls.executables = {}
        cls.report = dict(passed=False, driver_sha256=hashlib.sha256(DRIVER.read_bytes()).hexdigest(),
                          test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                          harness_sha256=hashlib.sha256(HARNESS.encode('utf-8')).hexdigest(),
                          physical_input_used=False, compiled_production_driver=True, cases=[])
        (cls.area / 'driver-under-test.c').write_text(cls.production, encoding='utf-8')
        (cls.area / 'harness.c').write_text(HARNESS, encoding='utf-8')
        for name, flags in (('r1', ['-DHIBY_R1']), ('ubsan', ['-DHIBY_R1', '-fsanitize=undefined', '-fno-sanitize-recover=all']),
                            ('generic', [])):
            executable = cls.area / name
            command = [*shlex.split(os.environ.get('CC', 'cc')), '-std=c99', '-D_POSIX_C_SOURCE=200809L', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                       '-DHAVE_TOUCHSCREEN', '-DHAVE_BUTTON_DATA', '-I', str(cls.area), *flags,
                       str(cls.area / 'harness.c'), '-o', str(executable)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            (cls.area / (name + '-compile.log')).write_text(result.stdout + result.stderr, encoding='utf-8')
            if result.returncode:
                raise AssertionError(result.stderr)
            cls.executables[name] = executable

    @classmethod
    def tearDownClass(cls):
        cls.report['passed'] = len(cls.report['cases']) == len(CASES) * 2 + 4 and all(
            item['exit_code'] != 0 if item.get('causal_mutant') else item['exit_code'] == 0
            for item in cls.report['cases'])
        (cls.area / 'report.json').write_text(json.dumps(cls.report, indent=2) + '\n', encoding='utf-8')
        print('Real Linux input evidence:', cls.area, flush=True)

    def run_case(self, case, targets=('r1', 'ubsan')):
        for target in targets:
            with self.subTest(target=target):
                result = subprocess.run([self.executables[target], case], capture_output=True, text=True,
                                        cwd=self.area, timeout=5, preexec_fn=disable_core_dump)
                self.report['cases'].append(dict(target=target, name=case, exit_code=result.returncode,
                                                 stdout=result.stdout, stderr=result.stderr))
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_queued_short_presses_keep_each_edge(self): self.run_case('queued-clicks')
    def test_emergency_chord_edges_are_preserved(self): self.run_case('chord-edges')
    def test_queued_swipe_frames_keep_coherent_coordinates(self): self.run_case('queued-touch')
    def test_queued_double_taps_keep_both_contacts(self): self.run_case('double-touch')
    def test_ev_key_touch_commits_with_its_coordinates(self): self.run_case('ev-key-touch')
    def test_repeats_do_not_fabricate_releases(self): self.run_case('hold-repeat')
    def test_poll_error_returns_without_spinning_or_releasing(self): self.run_case('poll-errors')
    def test_idle_and_disabled_touch_remain_inert(self): self.run_case('idle-and-disabled')
    def test_other_targets_keep_their_existing_sampling_policy(self): self.run_case('generic-policy', ('generic',))
    def test_foreign_syn_does_not_publish_partial_touch(self): self.run_case('multi-foreign-syn')
    def test_key_edge_uses_only_committed_touch(self): self.run_case('multi-key-mid-frame')
    def test_per_device_key_ownership_and_retirement(self): self.run_case('multi-owned-keys')
    def test_alternating_devices_are_not_starved(self): self.run_case('multi-fairness')
    def test_dropped_packet_recovery_preserves_other_device(self): self.run_case('multi-drop-isolation')
    def test_disable_cancels_held_touch_until_release(self): self.run_case('cancel-held-touch')
    def test_disabled_key_touch_cannot_reappear(self): self.run_case('cancel-disabled-key-touch')
    def test_disable_cancels_incomplete_frame(self): self.run_case('cancel-mid-frame')
    def test_continuous_readable_backlog_has_bounded_work(self): self.run_case('bounded-backlog')
    def test_bad_descriptors_cancel_without_spinning(self):
        for case in ('retire-invalid', 'retire-eof', 'retire-short', 'retire-fatal', 'retire-hup-again', 'retire-readable'):
            self.run_case(case)
    def test_transient_reads_are_bounded_without_releasing(self): self.run_case('transient-read')
    def test_dropped_packets_resynchronize_physical_keys(self): self.run_case('drop-recovery')
    def test_failed_resync_cancels_only_affected_keys(self): self.run_case('drop-query-failed')
    def test_dropped_touch_is_cancelled_until_a_fresh_contact(self): self.run_case('drop-touch')
    def test_known_released_mt_snapshot_allows_next_contact(self): self.run_case('drop-touch-known-up')
    def test_known_released_key_snapshot_allows_next_contact(self): self.run_case('drop-key-touch-up')
    def test_known_held_key_snapshot_stays_cancelled_until_release(self): self.run_case('drop-key-touch-held')

    def run_mutant(self, name, source, case):
        directory = self.area / name
        directory.mkdir()
        for header, content in HEADERS.items():
            (directory / header).write_text(content, encoding='utf-8')
        (directory / 'driver-under-test.c').write_text(source, encoding='utf-8')
        (directory / 'harness.c').write_text(HARNESS, encoding='utf-8')
        executable = directory / 'mutant'
        command = [*shlex.split(os.environ.get('CC', 'cc')), '-std=c99', '-D_POSIX_C_SOURCE=200809L',
                   '-O1', '-Wall', '-Wextra', '-Werror', '-DHIBY_R1', '-DHAVE_TOUCHSCREEN',
                   '-DHAVE_BUTTON_DATA', '-I', str(directory), str(directory / 'harness.c'), '-o', str(executable)]
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
        (directory / 'compile.log').write_text(compiled.stdout + compiled.stderr, encoding='utf-8')
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        result = subprocess.run([executable, case], capture_output=True, text=True,
                                cwd=directory, timeout=5, preexec_fn=disable_core_dump)
        self.report['cases'].append(dict(target=name, name=case, causal_mutant=True,
                                         exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr))
        self.assertNotEqual(result.returncode, 0, 'Mutant unexpectedly retained the corrected behavior')

    def test_restoring_drain_all_behavior_reproduces_lost_click(self):
        corrected = '            return r1_sample(data);'
        self.assertEqual(self.production.count(corrected), 1)
        self.run_mutant('drain-all-mutant', self.production.replace(
            corrected, '            continue;'), 'queued-clicks')

    def test_restoring_negative_poll_loop_reproduces_spin(self):
        corrected = 'if (poll(poll_fds, num_devices, 0) <= 0)'
        self.assertEqual(self.production.count(corrected), 1)
        self.run_mutant('negative-poll-mutant', self.production.replace(
            corrected, 'if (poll(poll_fds, num_devices, 0) == 0)'), 'poll-errors')

    def test_early_touch_commit_reproduces_partial_frame(self):
        corrected = '        r1_stage_touch(index, event->code, event->value);'
        self.assertEqual(self.production.count(corrected), 1)
        self.run_mutant('partial-frame-mutant', self.production.replace(corrected,
            '    {\n' + corrected + '\n        r1_commit_touch(index);\n    }'), 'multi-foreign-syn')


if __name__ == '__main__':
    unittest.main(verbosity=2)
