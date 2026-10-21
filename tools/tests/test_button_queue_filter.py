"""Exercise atomic queue filtering and the production button wrapper headlessly."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root
from test_accessibility_integration import balanced_definition


ROOT = Path(__file__).resolve().parents[2]
INPUTS = (
    "firmware/kernel/queue.c", "firmware/kernel/include/queue.h",
    "firmware/drivers/button_queue.c", "firmware/export/button.h",
    "tools/tests/test_button_queue_filter.py",
    "tools/tests/test_accessibility_integration.py", "tools/project_materials.py",
)


def function(source, name):
    return balanced_definition(source, r"^[ \t]*(?:static\s+)?(?:inline\s+)?"
                               r"(?:void|bool|int|long|intptr_t|unsigned(?:\s+int)?)\s+"
                               + re.escape(name) + r"\s*\([^;{}]*\)\s*\{")


PREAMBLE = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#define HAVE_TOUCHSCREEN
#define IF_COP(...) __VA_ARGS__
#define LIKELY(value) (value)
#define UNLIKELY(value) (value)
#define TIMEOUT_NOBLOCK 0
#define TIMEOUT_BLOCK -1
#define WAKEUP_RELEASE 1
#define WAKEUP_DEFAULT 2
#define CPU_MODE_THREAD_CONTEXT 0
#define ASSERT_CPU_MODE(mode, level) ((void)(mode), (void)(level))
struct thread_entry { intptr_t retval; unsigned int wakes; };
struct __wait_queue { struct thread_entry *first; };
struct corelock { unsigned int held; };
static unsigned int checks;
static void fixture_check(bool condition, const char *expression, unsigned int line)
{
    ++checks;
    if (!condition) { fprintf(stderr, "line %u: %s\n", line, expression); exit(1); }
}
#define CHECK(value) fixture_check((value), #value, __LINE__)
'''


KERNEL = r'''
_Static_assert(QUEUE_LENGTH == 32, "The fix must not increase queue capacity");
static struct event_queue button_queue;
static intptr_t button_data;
static struct corelock *held_lock;
static int irq_level;
static unsigned int locks, restores, overflow_checks, producer_attempts, producer_posts;
static bool producer_pending, producer_running, record_overflow;
static int producer_observed_count;
static long producer_id;
static intptr_t producer_data;
static struct thread_entry current_thread;
static long current_tick;

static void kernel_assert(bool condition)
{
    if (!condition) { ++overflow_checks; CHECK(record_overflow); }
}
#define KERNEL_ASSERT(condition, ...) kernel_assert(condition)
static int disable_irq_save(void)
{
    int previous = irq_level;
    irq_level = 1;
    return previous;
}
static void disable_irq(void) { irq_level = 1; }
static void corelock_lock(struct corelock *lock)
{
    CHECK(irq_level == 1 && !lock->held && !held_lock);
    lock->held = 1;
    held_lock = lock;
    ++locks;
    if (producer_pending && !producer_running) ++producer_attempts;
}
static void corelock_unlock(struct corelock *lock)
{
    CHECK(irq_level == 1 && lock->held == 1 && held_lock == lock);
    held_lock = NULL;
    lock->held = 0;
}
static void restore_irq(int previous)
{
    CHECK(irq_level == 1 && !held_lock);
    irq_level = previous;
    ++restores;
    if (!previous && producer_pending && !producer_running)
    {
        producer_pending = false;
        producer_running = true;
        producer_observed_count = queue_count(&button_queue);
        CHECK(!queue_full(&button_queue));
        ++producer_posts;
        queue_post(&button_queue, producer_id, producer_data);
        producer_running = false;
    }
}
static void wakeup_thread(struct thread_entry *thread, int reason)
{
    CHECK(irq_level == 1 && held_lock && reason == WAKEUP_RELEASE);
    ++thread->wakes;
}
static void queue_wake_waiter(struct event_queue *queue)
{
    CHECK(held_lock == &queue->cl && irq_level == 1);
}
static struct thread_entry *__running_self_entry(void) { return &current_thread; }
static void block_thread(struct thread_entry *thread, int ticks,
                         struct __wait_queue *waiters, void *blocker)
{
    (void)thread; (void)ticks; (void)waiters; (void)blocker; CHECK(false);
}
static void switch_thread(void) { CHECK(false); }
static bool wait_queue_try_remove(struct thread_entry *thread) { (void)thread; return true; }
static long get_tmo_tick(struct thread_entry *thread) { (void)thread; return current_tick; }
static void button_queue_wait(struct queue_event *event, int timeout)
{
    queue_wait_w_tmo(&button_queue, event, timeout);
}
'''


CASES = r'''
static const long preserved_mask = SYS_EVENT | BUTTON_MULTIMEDIA | BUTTON_REL;

static void reset_queue(unsigned int start)
{
    CHECK(!held_lock && !irq_level);
    memset(&button_queue, 0, sizeof(button_queue));
    button_queue.read = button_queue.write = start;
    locks = restores = overflow_checks = producer_attempts = producer_posts = 0;
    producer_pending = producer_running = record_overflow = false;
    producer_observed_count = -1;
    button_data = 0;
}

static intptr_t payload(unsigned int index)
{
    return index & 1 ? INTPTR_MIN + index : INTPTR_MAX - index;
}

static bool keep(long identifier, long mask, long exception)
{
    return (identifier & mask) || identifier == exception;
}

static void expect_events(const struct queue_event *expected, unsigned int count)
{
    CHECK(queue_count(&button_queue) == (int)count);
    for (unsigned int index = 0; index < count; ++index)
    {
        struct queue_event event;
        queue_wait_w_tmo(&button_queue, &event, 0);
        CHECK(event.id == expected[index].id && event.data == expected[index].data);
    }
    struct queue_event event = { 123, 456 };
    queue_wait_w_tmo(&button_queue, &event, 0);
    CHECK(event.id == SYS_TIMEOUT && event.data == 0);
    CHECK(!held_lock && !irq_level && !overflow_checks);
}

static void generic_case(void)
{
    const unsigned int starts[] = { 0, QUEUE_LENGTH - 1, UINT_MAX - 17, UINT_MAX };
    const unsigned int lengths[] = { 0, 1, 7, QUEUE_LENGTH - 1, QUEUE_LENGTH };
    const long identifiers[] = { 0, 1, 2, 3, 4, 5, 0x42, -1, LONG_MIN, LONG_MAX,
        SYS_USB_CONNECTED, SYS_USB_DISCONNECTED, SYS_POWEROFF,
        BUTTON_REDRAW, BUTTON_REL | 1, BUTTON_REPEAT | 1 };
    const long masks[] = { 0, 4, SYS_EVENT, preserved_mask, -1 };
    for (unsigned int start = 0; start < sizeof(starts) / sizeof(*starts); ++start)
        for (unsigned int length = 0; length < sizeof(lengths) / sizeof(*lengths); ++length)
            for (unsigned int mask = 0; mask < sizeof(masks) / sizeof(*masks); ++mask)
            {
                reset_queue(starts[start]);
                struct queue_event expected[QUEUE_LENGTH];
                unsigned int retained = 0;
                for (unsigned int index = 0; index < lengths[length]; ++index)
                {
                    long identifier = identifiers[index % (sizeof(identifiers) / sizeof(*identifiers))];
                    queue_post(&button_queue, identifier, payload(index));
                    if (keep(identifier, masks[mask], 0x42))
                        expected[retained++] = (struct queue_event){ identifier, payload(index) };
                }
                unsigned int before_locks = locks;
                queue_remove_except(&button_queue, masks[mask], 0x42);
                CHECK(locks == before_locks + 1);
                queue_remove_except(&button_queue, masks[mask], 0x42);
                expect_events(expected, retained);
            }
}

static void wrapper_case(void)
{
    const long identifiers[] = {
        1, BUTTON_REPEAT | 1, BUTTON_TOUCHSCREEN, BUTTON_TOUCHSCREEN | BUTTON_REPEAT,
        0x01000001, SYS_USB_CONNECTED, SYS_USB_DISCONNECTED, SYS_POWEROFF,
        SYS_REBOOT, SYS_CHARGER_CONNECTED, SYS_CHARGER_DISCONNECTED,
        SYS_BATTERY_UPDATE, BUTTON_REL | 1, BUTTON_REPEAT | BUTTON_REL | 1,
        BUTTON_TOUCHSCREEN | BUTTON_REL, BUTTON_REDRAW,
        BUTTON_MULTIMEDIA_PLAYPAUSE, BUTTON_MULTIMEDIA_STOP, BUTTON_MULTIMEDIA_PREV,
        BUTTON_MULTIMEDIA_NEXT, BUTTON_MULTIMEDIA_REW, BUTTON_MULTIMEDIA_FFWD,
        BUTTON_MULTIMEDIA_VOLUME_UP, BUTTON_MULTIMEDIA_VOLUME_DOWN,
        BUTTON_REDRAW | 1, 0
    };
    reset_queue(UINT_MAX - 12);
    struct queue_event expected[QUEUE_LENGTH];
    unsigned int retained = 0;
    for (unsigned int index = 0; index < sizeof(identifiers) / sizeof(*identifiers); ++index)
    {
        queue_post(&button_queue, identifiers[index], payload(index));
        if (keep(identifiers[index], preserved_mask, BUTTON_REDRAW))
            expected[retained++] = (struct queue_event){ identifiers[index], payload(index) };
    }
    button_data = INTPTR_MIN + 17;
    button_clear_queue_preserve_events();
    CHECK(button_get_data() == INTPTR_MIN + 17);
    expect_events(expected, retained);
}

static void producer_case(void)
{
    reset_queue(UINT_MAX - 15);
    struct queue_event expected[QUEUE_LENGTH];
    unsigned int retained = 0;
    for (unsigned int index = 0; index < QUEUE_LENGTH; ++index)
    {
        long identifier = index == 0 ? 1 : index == 1 ? SYS_POWEROFF : SYS_BATTERY_UPDATE;
        queue_post(&button_queue, identifier, payload(index));
        if (index) expected[retained++] = (struct queue_event){ identifier, payload(index) };
    }
    CHECK(queue_full(&button_queue));
    producer_pending = true;
    producer_id = SYS_USB_DISCONNECTED;
    producer_data = INTPTR_MIN + 991;
    unsigned int before_locks = locks;
    button_clear_queue_preserve_events();
    CHECK(producer_attempts == 1 && producer_posts == 1);
    CHECK(producer_observed_count == QUEUE_LENGTH - 1);
    CHECK(locks == before_locks + 2 && !overflow_checks);
    expected[retained++] = (struct queue_event){ producer_id, producer_data };
    expect_events(expected, retained);
}

static void legacy_get_repost_filter(void)
{
    int remaining = button_queue_count();
    while (remaining-- > 0)
    {
        int button = button_get_w_tmo(TIMEOUT_NOBLOCK);
        intptr_t data = button_get_data();
        if ((button & (SYS_EVENT | BUTTON_MULTIMEDIA | BUTTON_REL)) || button == BUTTON_REDRAW)
            button_queue_post(button, data);
    }
}

static void negative_case(void)
{
    reset_queue(0);
    for (unsigned int index = 0; index < QUEUE_LENGTH; ++index)
        queue_post(&button_queue, index == 1 ? SYS_POWEROFF : SYS_BATTERY_UPDATE, index);
    producer_pending = record_overflow = true;
    producer_id = SYS_USB_DISCONNECTED;
    producer_data = 991;
    legacy_get_repost_filter();
    CHECK(producer_posts == 1 && producer_observed_count == QUEUE_LENGTH - 1);
    CHECK(overflow_checks > 0 && queue_count(&button_queue) == QUEUE_LENGTH + 1);
    for (unsigned int index = 0; index < QUEUE_LENGTH; ++index)
        CHECK(button_queue.events[index].id != SYS_POWEROFF);
}

static void clear_pressed_scope_case(void)
{
    const unsigned int starts[] = { 0, QUEUE_LENGTH - 1, UINT_MAX - 17 };
    const unsigned int lengths[] = { 0, 1, 13, QUEUE_LENGTH - 1, QUEUE_LENGTH };
    const long identifiers[] = {
        1, BUTTON_REPEAT | 1, BUTTON_TOUCHSCREEN, BUTTON_TOUCHSCREEN | BUTTON_REPEAT,
        SYS_USB_CONNECTED, SYS_USB_DISCONNECTED, SYS_POWEROFF, SYS_TIMEOUT,
        SYS_REBOOT, SYS_CHARGER_CONNECTED, SYS_CHARGER_DISCONNECTED,
        BUTTON_REL | 1, BUTTON_REPEAT | BUTTON_REL | 1, BUTTON_TOUCHSCREEN | BUTTON_REL,
        BUTTON_MULTIMEDIA_PLAYPAUSE, BUTTON_MULTIMEDIA_STOP, BUTTON_MULTIMEDIA_PREV,
        BUTTON_MULTIMEDIA_NEXT, BUTTON_MULTIMEDIA_REW, BUTTON_MULTIMEDIA_FFWD,
        BUTTON_MULTIMEDIA_VOLUME_UP, BUTTON_MULTIMEDIA_VOLUME_DOWN,
        BUTTON_REDRAW, BUTTON_REDRAW | 1, BUTTON_MULTIMEDIA | BUTTON_REL,
        BUTTON_REDRAW | BUTTON_REL, 0, 0x01000001, 0x01000001 | BUTTON_REL,
        SYS_BATTERY_UPDATE, SYS_USB_CONNECTED | BUTTON_MULTIMEDIA,
        BUTTON_REPEAT | BUTTON_REDRAW
    };
    _Static_assert(sizeof(identifiers) / sizeof(*identifiers) == QUEUE_LENGTH,
                   "Exercise the exact full legacy queue");
    for (unsigned int start = 0; start < sizeof(starts) / sizeof(*starts); ++start)
        for (unsigned int length = 0; length < sizeof(lengths) / sizeof(*lengths); ++length)
        {
            reset_queue(starts[start]);
            struct queue_event expected[QUEUE_LENGTH];
            unsigned int retained = 0;
            for (unsigned int index = 0; index < lengths[length]; ++index)
            {
                queue_post(&button_queue, identifiers[index], payload(index));
                if (identifiers[index] & (BUTTON_REL | SYS_EVENT))
                    expected[retained++] = (struct queue_event){ identifiers[index], payload(index) };
            }
            unsigned int before_locks = locks;
            button_clear_pressed();
            CHECK(locks == before_locks + 1);
            button_clear_pressed();
            expect_events(expected, retained);
        }
}

static void clear_pressed_producer_case(void)
{
    reset_queue(UINT_MAX - 15);
    struct queue_event expected[QUEUE_LENGTH];
    unsigned int retained = 0;
    for (unsigned int index = 0; index < QUEUE_LENGTH; ++index)
    {
        long identifier = index == 0 ? BUTTON_MULTIMEDIA_PLAYPAUSE :
            index == 1 ? SYS_POWEROFF : SYS_BATTERY_UPDATE;
        queue_post(&button_queue, identifier, payload(index));
        if (index) expected[retained++] = (struct queue_event){ identifier, payload(index) };
    }
    CHECK(queue_full(&button_queue));
    producer_pending = true;
    producer_id = SYS_USB_DISCONNECTED;
    producer_data = INTPTR_MIN + 991;
    unsigned int before_locks = locks;
    button_clear_pressed();
    CHECK(producer_attempts == 1 && producer_posts == 1);
    CHECK(producer_observed_count == QUEUE_LENGTH - 1);
    CHECK(locks == before_locks + 2 && !overflow_checks);
    expected[retained++] = (struct queue_event){ producer_id, producer_data };
    expect_events(expected, retained);
}

static void old_clear_pressed_get_repost_control(void)
{
    long button;
    for (int count = queue_count(&button_queue); count > 0; --count)
    {
        button = button_get(false);
        if (button & (BUTTON_REL | SYS_EVENT))
            button_queue_post(button, button_data);
    }
}

static void clear_pressed_negative_case(void)
{
    const long identifiers[] = {
        BUTTON_MULTIMEDIA_PLAYPAUSE, BUTTON_REDRAW, 1, BUTTON_REL | 1,
        SYS_USB_CONNECTED, BUTTON_MULTIMEDIA | BUTTON_REL,
        BUTTON_REDRAW | BUTTON_REL, SYS_POWEROFF
    };
    reset_queue(QUEUE_LENGTH - 1);
    struct queue_event expected[QUEUE_LENGTH];
    unsigned int retained = 0;
    for (unsigned int index = 0; index < sizeof(identifiers) / sizeof(*identifiers); ++index)
    {
        queue_post(&button_queue, identifiers[index], payload(index));
        if (identifiers[index] & (BUTTON_REL | SYS_EVENT))
            expected[retained++] = (struct queue_event){ identifiers[index], payload(index) };
    }
    CHECK(retained == 5);
    old_clear_pressed_get_repost_control();
    expect_events(expected, retained);
    reset_queue(0);
    for (unsigned int index = 0; index < QUEUE_LENGTH; ++index)
        queue_post(&button_queue, index == 1 ? SYS_POWEROFF : SYS_BATTERY_UPDATE, index);
    producer_pending = record_overflow = true;
    producer_id = SYS_USB_DISCONNECTED;
    producer_data = 991;
    old_clear_pressed_get_repost_control();
    CHECK(producer_posts == 1 && producer_observed_count == QUEUE_LENGTH - 1);
    CHECK(overflow_checks > 0 && queue_count(&button_queue) == QUEUE_LENGTH + 1);
    for (unsigned int index = 0; index < QUEUE_LENGTH; ++index)
        CHECK(button_queue.events[index].id != SYS_POWEROFF);
}

#ifdef HAVE_EXTENDED_MESSAGING_AND_NAME
static void sender_case(bool explicit_reply)
{
    const unsigned int starts[] = { 0, QUEUE_LENGTH - 1, UINT_MAX - 15 };
    for (unsigned int start = 0; start < sizeof(starts) / sizeof(*starts); ++start)
    {
        reset_queue(starts[start]);
        struct queue_sender_list senders;
        struct thread_entry threads[QUEUE_LENGTH];
        struct thread_entry inflight = { -881, 0 };
        memset(&senders, 0, sizeof(senders));
        memset(threads, 0, sizeof(threads));
        button_queue.send = &senders;
        senders.curr_sender = &inflight;
        struct queue_event expected[QUEUE_LENGTH];
        struct thread_entry *retained_senders[QUEUE_LENGTH];
        unsigned int retained = 0;
        for (unsigned int index = 0; index < QUEUE_LENGTH; ++index)
        {
            unsigned int kind = (index + start) % 3;
            long identifier = kind == 0 ? 1 : kind == 1 ? SYS_POWEROFF : BUTTON_REDRAW;
            queue_post(&button_queue, identifier, payload(index));
            threads[index].retval = -999;
            senders.senders[(button_queue.write - 1) & QUEUE_LENGTH_MASK] = &threads[index];
            if (kind)
            {
                retained_senders[retained] = &threads[index];
                expected[retained++] = (struct queue_event){ identifier, payload(index) };
            }
        }
        button_clear_queue_preserve_events();
        CHECK(senders.curr_sender == &inflight && inflight.wakes == 0 && inflight.retval == -881);
        CHECK(queue_count(&button_queue) == (int)retained);
        for (unsigned int index = 0; index < QUEUE_LENGTH; ++index)
        {
            bool removed = (index + start) % 3 == 0;
            CHECK(threads[index].wakes == (removed ? 1u : 0u));
            CHECK(threads[index].retval == (removed ? 0 : -999));
            unsigned int occurrences = 0;
            for (unsigned int slot = 0; slot < QUEUE_LENGTH; ++slot)
                occurrences += senders.senders[slot] == &threads[index];
            CHECK(occurrences == (removed ? 0u : 1u));
        }
        for (unsigned int index = 0; index < retained; ++index)
        {
            unsigned int slot = (button_queue.read + index) & QUEUE_LENGTH_MASK;
            CHECK(senders.senders[slot] == retained_senders[index]);
            CHECK(button_queue.events[slot].id == expected[index].id);
            CHECK(button_queue.events[slot].data == expected[index].data);
        }
        while (!queue_full(&button_queue)) queue_post(&button_queue, 1, 55);
        for (unsigned int index = 0; index < retained; ++index)
            CHECK(retained_senders[index]->wakes == 0);
        for (unsigned int index = 0; index < retained; ++index)
        {
            struct queue_event event;
            queue_wait_w_tmo(&button_queue, &event, 0);
            CHECK(inflight.wakes == 1 && inflight.retval == 0);
            CHECK(event.id == expected[index].id && event.data == expected[index].data);
            CHECK(senders.curr_sender == retained_senders[index]);
            CHECK(retained_senders[index]->wakes == 0);
            if (explicit_reply)
            {
                queue_reply(&button_queue, 707);
                CHECK(retained_senders[index]->wakes == 1 && retained_senders[index]->retval == 707);
                CHECK(!senders.curr_sender);
            }
            else if (index)
                CHECK(retained_senders[index - 1]->wakes == 1 && retained_senders[index - 1]->retval == 0);
        }
        struct queue_event event;
        queue_wait_w_tmo(&button_queue, &event, 0);
        for (unsigned int index = 0; index < retained; ++index)
        {
            CHECK(retained_senders[index]->wakes == 1);
            CHECK(retained_senders[index]->retval == (explicit_reply ? 707 : 0));
        }
        CHECK(!senders.curr_sender && !overflow_checks);
        button_clear_queue_preserve_events();
        CHECK(queue_count(&button_queue) == 0);
        CHECK(inflight.wakes == 1);
        button_queue.send = NULL;
    }
}
#endif

int main(int argc, char **argv)
{
    CHECK(argc == 2);
    if (!strcmp(argv[1], "generic")) generic_case();
    else if (!strcmp(argv[1], "wrapper")) wrapper_case();
    else if (!strcmp(argv[1], "producer")) producer_case();
    else if (!strcmp(argv[1], "negative")) negative_case();
    else if (!strcmp(argv[1], "clear-pressed-scope")) clear_pressed_scope_case();
    else if (!strcmp(argv[1], "clear-pressed-producer")) clear_pressed_producer_case();
    else if (!strcmp(argv[1], "clear-pressed-negative")) clear_pressed_negative_case();
#ifdef HAVE_EXTENDED_MESSAGING_AND_NAME
    else if (!strcmp(argv[1], "senders-reply")) sender_case(true);
    else if (!strcmp(argv[1], "senders-auto")) sender_case(false);
#endif
    else CHECK(false);
    printf("{\"checks\":%u,\"capacity\":%u,\"producer_posts\":%u,\"overflow_checks\":%u}\n",
           checks, QUEUE_LENGTH, producer_posts, overflow_checks);
    return 0;
}
'''


def fixture(sources):
    queue = sources["firmware/kernel/queue.c"]
    buttons = sources["firmware/drivers/button_queue.c"]
    queue_header = re.sub(r'^\s*#include[^\n]*', '', sources["firmware/kernel/include/queue.h"], flags=re.M)
    button_header = sources["firmware/export/button.h"]
    start = button_header.index("#define BUTTON_NONE")
    end = button_header.index("#ifdef HAVE_TOUCHSCREEN", start)
    sender_names = ("queue_release_sender_inner", "queue_release_sender",
                    "queue_do_unblock_sender", "queue_do_auto_reply", "queue_do_fetch_sender")
    senders = "#ifdef HAVE_EXTENDED_MESSAGING_AND_NAME\n"
    senders += "\n".join(function(queue, name) for name in sender_names)
    senders += "\n#else\n#define queue_do_unblock_sender(send, index)\n"
    senders += "#define queue_do_auto_reply(send)\n#define queue_do_fetch_sender(send, index)\n#endif\n"
    unit = PREAMBLE + queue_header + button_header[start:end] + KERNEL + senders
    unit += "\n".join(function(queue, name) for name in (
        "queue_post", "queue_count", "queue_full", "queue_wait_w_tmo", "queue_remove_except"))
    unit += "\n#ifdef HAVE_EXTENDED_MESSAGING_AND_NAME\n" + function(queue, "queue_reply") + "#endif\n"
    unit += "\n".join(function(buttons, name) for name in (
        "button_queue_post", "button_queue_count", "button_get_w_tmo", "button_get", "button_get_data",
        "button_clear_queue_preserve_events", "button_clear_pressed"))
    return unit + CASES


@unittest.skipIf(sys.platform == "win32", "The bounded POSIX fixture runs under WSL")
class ButtonQueueFilterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
        cls.area = project_materials_root(ROOT) / "r1-input-refinements-20261017" / "button-queue-filter-tests" / stamp
        cls.area.mkdir(parents=True, exist_ok=False)
        cls.runs, cls.failed_tests, cls.completed_methods = [], [], []
        cls.setup_error = None
        cls.hashes = {}
        cls.binaries = {}
        cls.addClassCleanup(cls.report)
        try:
            cls.hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in INPUTS}
            sources = {name: (ROOT / name).read_text(encoding="utf-8") for name in INPUTS}
            generated = cls.area / "queue-filter.c"
            generated.write_text(fixture(sources), encoding="utf-8")
            compiler = shlex.split(os.environ.get("CC", "cc"))
            if not compiler or not shutil.which(compiler[0]):
                raise RuntimeError("A native C compiler is required; run under WSL")
            for variant in ("plain", "extended"):
                binary = cls.area / variant
                command = compiler + ["-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-Wno-unused-function", "-fsanitize=undefined", "-fno-sanitize-recover=all",
                    str(generated), "-o", str(binary)]
                if variant == "extended":
                    command.append("-DHAVE_EXTENDED_MESSAGING_AND_NAME")
                result = subprocess.run(command, capture_output=True, text=True, timeout=45)
                record = {"kind": "compile", "variant": variant, "command": command,
                          "exit": result.returncode, "stdout": result.stdout, "stderr": result.stderr,
                          "passed": result.returncode == 0}
                cls.runs.append(record)
                (cls.area / (variant + "-compile.json")).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
                if result.returncode:
                    raise RuntimeError(result.stderr)
                cls.binaries[variant] = binary
        except Exception as error:
            cls.setup_error = repr(error)
            raise
        print("Button queue filter evidence:", cls.area, flush=True)

    @classmethod
    def report(cls):
        try:
            after = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in INPUTS}
            stable = cls.hashes == after
        except Exception as error:
            after, stable = {"error": repr(error)}, False
        expected = unittest.defaultTestLoader.getTestCaseNames(cls)
        passed = (cls.setup_error is None and stable and not cls.failed_tests
                  and sorted(cls.completed_methods) == sorted(expected)
                  and len(cls.binaries) == 2 and len(cls.runs) == 18
                  and all(record["passed"] for record in cls.runs))
        report = {"source_project": str(ROOT), "source_hashes_before": cls.hashes,
                  "source_hashes_after": after, "sources_stable": stable,
                  "expected_methods": expected, "completed_methods": cls.completed_methods,
                  "failed_tests": cls.failed_tests, "setup_error": cls.setup_error,
                  "runs": cls.runs, "passed": passed,
                  "controlled_kernel_scheduling": True, "real_parallel_threads": False,
                  "full_product_build": False, "host_hardware_used": False}
        (cls.area / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if not stable:
            raise AssertionError("Queue filter inputs changed during the focused run")

    def tearDown(self):
        self.__class__.completed_methods.append(self._testMethodName)
        prefix = self.__class__.__module__ + "." + self.__class__.__name__ + "."
        result = self._outcome.result
        self.__class__.failed_tests = [case.id() for case, _ in result.failures + result.errors
                                      if case.id().startswith(prefix)]

    def run_case(self, scenario, variants=("plain", "extended")):
        for variant in variants:
            with self.subTest(variant=variant):
                command = [str(self.binaries[variant]), scenario]
                try:
                    result = subprocess.run(command, capture_output=True, text=True, timeout=15,
                        env={**os.environ, "UBSAN_OPTIONS": "halt_on_error=1:print_stacktrace=1"})
                    record = {"kind": "runtime", "variant": variant, "scenario": scenario,
                              "command": command, "exit": result.returncode,
                              "stdout": result.stdout, "stderr": result.stderr,
                              "passed": result.returncode == 0}
                    self.__class__.runs.append(record)
                    if result.returncode == 0:
                        record.update(json.loads(result.stdout))
                except Exception as error:
                    self.__class__.runs.append({"kind": "runtime", "variant": variant,
                        "scenario": scenario, "passed": False, "error": repr(error)})
                    raise
                finally:
                    (self.area / (variant + "-" + scenario + ".json")).write_text(
                        json.dumps(self.runs[-1], indent=2) + "\n", encoding="utf-8")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(record["capacity"], 32)

    def test_generic_filter_fifo_payloads_empty_full_and_index_wrap(self):
        self.run_case("generic")

    def test_real_button_wrapper_preserves_system_release_redraw_and_media(self):
        self.run_case("wrapper")

    def test_capacity_32_producer_at_atomic_filter_boundary(self):
        self.run_case("producer")

    def test_negative_old_get_repost_loses_shutdown_and_overflows(self):
        self.run_case("negative")

    def test_extended_senders_survive_compaction_and_receive_explicit_reply(self):
        self.run_case("senders-reply", ("extended",))

    def test_extended_senders_removal_and_dequeue_auto_reply(self):
        self.run_case("senders-auto", ("extended",))

    def test_real_clear_pressed_preserves_only_system_and_release_events(self):
        self.run_case("clear-pressed-scope")

    def test_clear_pressed_full_capacity_producer_keeps_fifo_and_shutdown(self):
        self.run_case("clear-pressed-producer")

    def test_old_clear_pressed_control_matches_scope_but_loses_shutdown(self):
        self.run_case("clear-pressed-negative")


if __name__ == "__main__":
    unittest.main()
