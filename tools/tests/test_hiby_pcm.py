"""Compile and exercise the actual isolated HiBy PCM driver without a player."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import selectors
import shutil
import signal
import struct
import subprocess
import sys
import time
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root
from test_tts_coverage import extract_block
from test_tts_mixer_restart import function


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "firmware/target/hosted/hiby/pcm-hiby.c"
HEADER = SOURCE.with_suffix(".h")
RACE_FIXTURE = Path(__file__).with_name("fixtures") / "hiby_pcm_route_race_fixture.c"
LIFECYCLE_FIXTURE = Path(__file__).with_name("fixtures") / "hiby_pcm_lifecycle_fixture.c"
STATUS_FIXTURE = Path(__file__).with_name("fixtures") / "hiby_pcm_output_status_fixture.c"
MIXER_INPUTS = ("firmware/pcm_mixer.c", "firmware/pcm.c", "firmware/export/pcm-internal.h",
                "firmware/export/pcm_mixer.h", "firmware/asm/pcm-mixer.c", "firmware/general.c")

def process_state(pid):
    fields = Path(f"/proc/{pid}/stat").read_text().rpartition(")")[2].split()
    return {"pid": pid, "state": fields[0], "group": int(fields[2]),
            "session": int(fields[3]), "start_ticks": int(fields[19])}


def session_members(session):
    members = []
    for path in Path("/proc").iterdir():
        if not path.name.isdecimal():
            continue
        try:
            member = process_state(int(path.name))
        except (FileNotFoundError, ProcessLookupError):
            continue
        if member["session"] == session:
            members.append(member)
    return members


def cleanup_session(leader, record):
    sent, errors = set(), []
    record.update(signals=[], reaped=[], survivors=[])
    for signum, grace in ((signal.SIGTERM, 0.2), (signal.SIGKILL, 1.0)):
        deadline = time.monotonic() + grace
        while True:
            current = process_state(leader["pid"])
            if current["start_ticks"] != leader["start_ticks"] or current["session"] != leader["pid"]:
                raise RuntimeError("Owned session leader identity changed; refusing signals")
            members = session_members(leader["pid"])
            live = [member for member in members if member["state"] not in ("Z", "X")]
            for member in members:
                identity = (member["pid"], member["start_ticks"], signum)
                if member["pid"] == leader["pid"] and member["state"] in ("Z", "X"):
                    continue
                if identity in sent and member["state"] != "Z":
                    continue
                descriptor = None
                try:
                    descriptor = os.pidfd_open(member["pid"])
                    verified = process_state(member["pid"])
                    if verified["start_ticks"] != member["start_ticks"] or verified["session"] != leader["pid"]:
                        continue
                    if verified["state"] == "Z":
                        try:
                            if os.waitid(os.P_PIDFD, descriptor, os.WEXITED | os.WNOHANG) is not None:
                                record["reaped"].append(member["pid"])
                        except ChildProcessError:
                            pass
                        continue
                    signal.pidfd_send_signal(descriptor, signum)
                    record["signals"].append(dict(member, signal=signum.name))
                    sent.add(identity)
                except (ProcessLookupError, FileNotFoundError):
                    pass
                except OSError as error:
                    errors.append(repr(error))
                    sent.add(identity)
                finally:
                    if descriptor is not None:
                        os.close(descriptor)
            if not live:
                if errors:
                    raise RuntimeError("Owned session signal errors: " + repr(errors))
                return
            if time.monotonic() >= deadline:
                break
            time.sleep(0.01)
    record["survivors"] = [member for member in session_members(leader["pid"])
                           if member["state"] not in ("Z", "X")]
    raise RuntimeError("Owned session cleanup did not complete: " + repr(record["survivors"]) + repr(errors))


def run_isolated_case(command, environment=None, timeout=12, record=None, cwd=None):
    if not sys.platform.startswith("linux") or not hasattr(os, "P_PIDFD") or not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
        raise RuntimeError("PCM case isolation requires Linux pidfds and non-reaping waitid")
    record = {} if record is None else record
    process = subprocess.Popen(command, env=environment, cwd=cwd, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    output = {"stdout": bytearray(), "stderr": bytearray()}
    primary, leader = None, None
    selector = None
    cleanup_errors = []
    try:
        leader = process_state(process.pid)
        if leader["session"] != process.pid or leader["group"] != process.pid or leader["session"] == os.getsid(0):
            raise RuntimeError("PCM case is not in its own session")
        record["owned_session"] = leader
        selector = selectors.DefaultSelector()
        for name in output:
            stream = getattr(process, name)
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, name)
        deadline = time.monotonic() + timeout
        while os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout, bytes(output["stdout"]), bytes(output["stderr"]))
            for selected, events in selector.select(min(remaining, 0.02)):
                data = os.read(selected.fileobj.fileno(), 65536)
                if data:
                    output[selected.data].extend(data)
                else:
                    selector.unregister(selected.fileobj)
    except BaseException as error:
        primary = error
        record["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        try:
            if leader is None:
                process.kill()
                raise RuntimeError("Could not verify owned session membership")
            cleanup_session(leader, record.setdefault("session_cleanup", {}))
        except BaseException as error:
            cleanup_errors.append(repr(error))
        if selector is not None:
            try:
                selector.close()
            except BaseException as error:
                cleanup_errors.append(repr(error))
        try:
            remaining_output, remaining_error = process.communicate(timeout=2)
            output["stdout"].extend(remaining_output)
            output["stderr"].extend(remaining_error)
        except BaseException as error:
            cleanup_errors.append(repr(error))
        finally:
            try:
                process.wait(timeout=2)
            except BaseException as error:
                cleanup_errors.append(repr(error))
            for name in output:
                try:
                    getattr(process, name).close()
                except BaseException as error:
                    cleanup_errors.append(repr(error))
        record.update(returncode=process.returncode, stdout=output["stdout"].decode(errors="replace"),
                      stderr=output["stderr"].decode(errors="replace"), cleanup_errors=cleanup_errors)
        if isinstance(primary, subprocess.TimeoutExpired):
            primary.output, primary.stderr = bytes(output["stdout"]), bytes(output["stderr"])
        if cleanup_errors:
            if primary is None:
                raise RuntimeError("PCM owned cleanup failed: " + repr(cleanup_errors))
            primary.add_note("PCM owned cleanup errors: " + repr(cleanup_errors))
    return subprocess.CompletedProcess(command, process.returncode, bytes(output["stdout"]), bytes(output["stderr"]))


SHIM = r'''
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define HW_NUM_FREQ 2
#define HW_FREQ_DEFAULT 0
#define PCM_NATIVE_VOLUME_TYPE 0
enum pcm_dma_status { PCM_DMAST_ERR_DMA = -1, PCM_DMAST_OK, PCM_DMAST_STARTED };
struct pcm_sink_caps {
    const unsigned long *samprs;
    uint8_t num_samprs, default_freq, volume_type;
};
struct pcm_sink_ops {
    void (*init)(void), (*postinit)(void);
    void (*set_freq)(uint16_t frequency);
    void (*lock)(void), (*unlock)(void);
    void (*play)(const void *address, size_t size);
    void (*stop)(void);
};
struct pcm_sink {
    struct pcm_sink_caps caps;
    const struct pcm_sink_ops ops;
    unsigned long pending_freq, configured_freq;
};
static const unsigned long hw_freq_sampr[2] = {44100, 48000};
void audiohw_preinit(void);
void audiohw_postinit(void);
bool pcm_play_dma_complete_callback(enum pcm_dma_status status, const void **address, size_t *size);
enum pcm_dma_status pcm_play_dma_status_callback(enum pcm_dma_status status);
void pcm_play_stop_int(void);
'''

PROGRAM = r'''
#define _GNU_SOURCE 1
#include <alsa/asoundlib.h>
#include <assert.h>
#include <fcntl.h>
#include <limits.h>
#include <pthread.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static void delay_ms(unsigned int milliseconds)
{
    struct timespec duration = {milliseconds / 1000, (long)(milliseconds % 1000) * 1000000};
    while (nanosleep(&duration, &duration) && errno == EINTR) {}
}

#ifdef FAKE_ALSA
static bool fake_bluetooth;
static unsigned int fake_writes;
static const char *fake_mode;
static bool mode_is(const char *mode)
{
    return fake_bluetooth && fake_mode && !strcmp(fake_mode, mode);
}
static void log_event(uint32_t event, const void *data, size_t size)
{
    const char *path = getenv("PCM_LOG");
    if (!path) return;
    int descriptor = open(path, O_WRONLY | O_CREAT | O_APPEND, 0600);
    assert(descriptor >= 0);
    unsigned char record[8192];
    uint32_t header[] = {event, fake_bluetooth, (uint32_t)size};
    assert(size + sizeof(header) <= sizeof(record));
    memcpy(record, header, sizeof(header));
    if (size) memcpy(record + sizeof(header), data, size);
    assert(write(descriptor, record, size + sizeof(header)) == (ssize_t)(size + sizeof(header)));
    close(descriptor);
}
int snd_pcm_open(snd_pcm_t **handle, const char *device, snd_pcm_stream_t stream, int mode)
{
    assert(stream == SND_PCM_STREAM_PLAYBACK && (mode & SND_PCM_NONBLOCK));
    fake_bluetooth = !strncmp(device, "bluealsa:", 9);
    fake_mode = getenv("PCM_MODE");
    log_event(1, NULL, 0);
    if (!fake_bluetooth && fake_mode && !strcmp(fake_mode, "local-open-fail")) return -ENODEV;
    if (mode_is("open-hang")) for (;;) delay_ms(100);
    if (mode_is("open-fail")) return -ENODEV;
    *handle = (snd_pcm_t *)(uintptr_t)1;
    return 0;
}
int snd_pcm_set_params(snd_pcm_t *handle, snd_pcm_format_t format, snd_pcm_access_t access,
    unsigned int channels, unsigned int rate, int resample, unsigned int latency)
{
    assert(handle && format == SND_PCM_FORMAT_S16_LE && access == SND_PCM_ACCESS_RW_INTERLEAVED);
    assert(channels == 2 && resample && rate >= 8000 && latency == 60000);
    log_event(6, &rate, sizeof(rate));
    if (mode_is("config-hang")) for (;;) delay_ms(100);
    return mode_is("config-fail") ? -EINVAL : 0;
}
int snd_pcm_prepare(snd_pcm_t *handle) { assert(handle); log_event(7, NULL, 0); return 0; }
int snd_pcm_resume(snd_pcm_t *handle) { assert(handle); log_event(8, NULL, 0); return 0; }
int snd_pcm_drop(snd_pcm_t *handle) { assert(handle); log_event(4, NULL, 0); return 0; }
int snd_pcm_drain(snd_pcm_t *handle)
{
    assert(handle);
    log_event(3, NULL, 0);
    if (mode_is("drain-hang")) for (;;) delay_ms(100);
    if (mode_is("drain-again")) return -EAGAIN;
    return 0;
}
int snd_pcm_close(snd_pcm_t *handle)
{
    assert(handle);
    log_event(5, NULL, 0);
    if (mode_is("close-hang")) for (;;) delay_ms(100);
    return 0;
}
snd_pcm_sframes_t snd_pcm_avail_update(snd_pcm_t *handle)
{
    assert(handle);
    return mode_is("removed-idle") ? -ENODEV : 4096;
}
snd_pcm_sframes_t snd_pcm_writei(snd_pcm_t *handle, const void *buffer, snd_pcm_uframes_t frames)
{
    assert(handle && frames && frames <= 1024);
    fake_writes++;
    if (mode_is("write-hang")) for (;;) delay_ms(100);
    if (mode_is("write-delay")) delay_ms(100);
    if (mode_is("write-again")) return -EAGAIN;
    if (mode_is("write-error")) return -ENODEV;
    if (mode_is("xrun") && fake_writes == 1) return -EPIPE;
    if (mode_is("suspend") && fake_writes == 1) return -ESTRPIPE;
    if (mode_is("partial") && frames > 73) frames = 73;
    log_event(2, buffer, frames * 4);
    return (snd_pcm_sframes_t)frames;
}
#endif

static bool hold_reaping;
static unsigned int spawn_attempts;
static unsigned int data_send_failures;
static int fail_next_data_errno;
static pthread_mutex_t shutdown_gate_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t shutdown_gate_changed = PTHREAD_COND_INITIALIZER;
static bool join_gate_hold, join_gate_entered;
static bool route_gate_hold, route_gate_entered, route_gate_owner_ready;
static pthread_t route_gate_owner;
static unsigned int shutdown_returns;
static unsigned int initialization_returns;
static pid_t test_fork(void)
{
    __atomic_add_fetch(&spawn_attempts, 1, __ATOMIC_RELAXED);
    return fork();
}
static ssize_t test_send(int descriptor, const void *data, size_t size, int flags)
{
    const uint32_t *header = data;
    if (fail_next_data_errno && size >= 16 && header[0] == 0x52425043u && header[1] == 2)
    {
        errno = fail_next_data_errno;
        fail_next_data_errno = 0;
        data_send_failures++;
        return -1;
    }
    return send(descriptor, data, size, flags);
}
static pid_t test_waitpid(pid_t process, int *status, int options)
{
    pthread_mutex_lock(&shutdown_gate_mutex);
    if (route_gate_hold && route_gate_owner_ready && pthread_equal(pthread_self(), route_gate_owner))
    {
        route_gate_entered = true;
        pthread_cond_broadcast(&shutdown_gate_changed);
        while (route_gate_hold)
            pthread_cond_wait(&shutdown_gate_changed, &shutdown_gate_mutex);
    }
    pthread_mutex_unlock(&shutdown_gate_mutex);
    return __atomic_load_n(&hold_reaping, __ATOMIC_ACQUIRE) ? 0 : waitpid(process, status, options);
}
static int test_pthread_join(pthread_t thread, void **result)
{
    pthread_mutex_lock(&shutdown_gate_mutex);
    if (join_gate_hold)
    {
        join_gate_entered = true;
        pthread_cond_broadcast(&shutdown_gate_changed);
        while (join_gate_hold)
            pthread_cond_wait(&shutdown_gate_changed, &shutdown_gate_mutex);
    }
    pthread_mutex_unlock(&shutdown_gate_mutex);
    return pthread_join(thread, result);
}
#ifdef PCM_TEST_STACK_MIN
#undef PTHREAD_STACK_MIN
#define PTHREAD_STACK_MIN PCM_TEST_STACK_MIN
static size_t requested_stack_size;
static int test_pthread_attr_setstacksize(pthread_attr_t *attributes, size_t stack_size)
{
    requested_stack_size = stack_size;
    if (stack_size < PTHREAD_STACK_MIN)
        return EINVAL;
    return pthread_attr_setstacksize(attributes, stack_size);
}
#define pthread_attr_setstacksize test_pthread_attr_setstacksize
#endif
#define waitpid test_waitpid
#define fork test_fork
#define send test_send
#define pthread_join test_pthread_join
#include "SOURCE_PATH"
#undef waitpid
#undef fork
#undef send
#undef pthread_join
#ifdef PCM_TEST_STACK_MIN
#undef pthread_attr_setstacksize
#endif

static int16_t audio[2048 * 2];
static unsigned int more_calls;
static unsigned int status_calls;
static bool invalid_more;
static bool cancel_route;
static int route_result;
static const char bt_device[] = "bluealsa:DEV=AA:BB:CC:DD:EE:FF,PROFILE=a2dp";

void audiohw_preinit(void) {}
void audiohw_postinit(void) {}
void pcm_play_stop_int(void) { builtin_pcm_sink.ops.stop(); }
bool pcm_play_dma_complete_callback(enum pcm_dma_status status, const void **address, size_t *size)
{
    assert(status == PCM_DMAST_OK);
    more_calls++;
    *address = NULL;
    *size = 0;
    if (invalid_more) return true;
    builtin_pcm_sink.ops.stop();
    return false;
}
enum pcm_dma_status pcm_play_dma_status_callback(enum pcm_dma_status status)
{
    status_calls++;
    return status;
}

static bool cancelled(void *context)
{
    (void)context;
    return __atomic_load_n(&cancel_route, __ATOMIC_ACQUIRE);
}
static void *route_thread(void *context)
{
    (void)context;
    pthread_mutex_lock(&shutdown_gate_mutex);
    route_gate_owner = pthread_self();
    route_gate_owner_ready = true;
    pthread_mutex_unlock(&shutdown_gate_mutex);
    route_result = pcm_alsa_switch_playback_device_cancellable(bt_device, cancelled, NULL);
    return NULL;
}
static void *shutdown_thread(void *context)
{
    (void)context;
    hiby_pcm_shutdown();
    __atomic_add_fetch(&shutdown_returns, 1, __ATOMIC_RELEASE);
    return NULL;
}
static void *initialization_thread(void *context)
{
    (void)context;
    builtin_pcm_sink.ops.init();
    __atomic_add_fetch(&initialization_returns, 1, __ATOMIC_RELEASE);
    return NULL;
}
static void wait_shutdown_gate(bool route)
{
    long long deadline = now_ms() + 700;
    for (;;)
    {
        pthread_mutex_lock(&shutdown_gate_mutex);
        bool entered = route ? route_gate_entered : join_gate_entered;
        pthread_mutex_unlock(&shutdown_gate_mutex);
        if (entered)
            return;
        assert(now_ms() < deadline);
        delay_ms(2);
    }
}
static bool wait_output(bool wanted_bluetooth, unsigned int timeout)
{
    long long deadline = now_ms() + timeout;
    while (now_ms() < deadline)
    {
        sink_lock();
        bool ready = active_helper.descriptor >= 0 && pcm_alsa_bluetooth_active() == wanted_bluetooth;
        sink_unlock();
        if (ready) return true;
        delay_ms(2);
    }
    return false;
}
static void wait_end(unsigned int timeout)
{
    long long deadline = now_ms() + timeout;
    while (now_ms() < deadline)
    {
        sink_lock();
        bool done = !playing && !stop_pending;
        sink_unlock();
        if (done) return;
        delay_ms(2);
    }
    assert(false);
}
static void verify_reaped(void)
{
    for (unsigned int iteration = 0; iteration < 100; iteration++)
    {
        bool remaining = false;
        pthread_mutex_lock(&pool_mutex);
        for (unsigned int position = 0; position < PCM_PROCESS_SLOTS; position++)
        {
            assert(process_pool[position] != -1);
            if (process_pool[position] > 0)
            {
                assert(retired_pool[position]);
                int status;
                pid_t result = waitpid(process_pool[position], &status, WNOHANG);
                if (result == process_pool[position] || (result < 0 && errno == ECHILD))
                    process_pool[position] = 0;
                else remaining = true;
            }
        }
        pthread_mutex_unlock(&pool_mutex);
        if (!remaining) return;
        delay_ms(2);
    }
    assert(false);
}

int main(int argc, char **argv)
{
    int helper = hiby_pcm_helper_main(argc, argv);
    if (helper >= 0) return helper;
    assert(argc == 2);
    const char *scenario = argv[1];
    for (size_t position = 0; position < sizeof(audio) / sizeof(audio[0]); position++)
        audio[position] = position % 2 ? -16000 : 16000;
    if (!strcmp(scenario, "helper-protocol") || !strcmp(scenario, "helper-eof"))
    {
        struct helper_process child;
        assert(!open_helper("null", 44100, &child, NULL, NULL));
        if (!strcmp(scenario, "helper-eof"))
        {
            close(child.descriptor);
            child.descriptor = -1;
            int status;
            pid_t result;
            long long deadline = now_ms() + 1500;
            do { result = waitpid(child.process, &status, WNOHANG); delay_ms(2); }
            while (!result && now_ms() < deadline);
            assert(result == child.process && WIFEXITED(status) && WEXITSTATUS(status) == 73);
            retire_helper(child);
            verify_reaped();
            return 0;
        }
        assert(send(child.descriptor, "bad", 3, MSG_NOSIGNAL) == 3);
        struct pcm_message message;
        int result;
        long long deadline = now_ms() + 1500;
        do { result = receive_message(child.descriptor, &message); delay_ms(2); }
        while (result == -EAGAIN && now_ms() < deadline);
        assert(!result && message.type == MESSAGE_ERROR && message.value == -EPROTO);
        retire_helper(child);
        verify_reaped();
        return 0;
    }
    if (!strcmp(scenario, "validation"))
    {
        assert(!valid_device(NULL));
        assert(!valid_device("bluealsa:DEV=AA:BB:GG:DD:EE:FF,PROFILE=a2dp"));
        assert(!valid_device("bluealsa:DEV=AA:BB:CC:DD:EE:FF,PROFILE=a2dp;reboot"));
        assert(pcm_alsa_switch_playback_device("invalid") == -EINVAL);
        assert(pcm_alsa_switch_playback_device(LOCAL_DEVICE) == -ENODEV);
        assert(volume_factor(-1000) == 0 && volume_factor(100) == 32768);
        assert(volume_factor(-60) > 16000 && volume_factor(-60) < 16500);
        int descriptors[2];
        assert(!socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_NONBLOCK, 0, descriptors));
        struct pcm_message message = {.magic = PCM_MAGIC};
        assert(send(descriptors[0], &message, 1, 0) == 1);
        assert(receive_message(descriptors[1], &message) == -EPROTO);
        assert(!send_message(descriptors[0], MESSAGE_DATA, 2, audio, 4));
        assert(!receive_message(descriptors[1], &message) && message.length == 4);
        assert(send_message(descriptors[0], MESSAGE_DATA, 2, audio, 3) == -EINVAL);
        close(descriptors[0]); close(descriptors[1]);
        return 0;
    }
    if (!strcmp(scenario, "closed-fds"))
    {
        close(0); close(1); close(2);
    }
#ifndef FAKE_ALSA
    pcm_alsa_set_playback_device("null");
#endif
    builtin_pcm_sink.ops.init();
    if (!strcmp(scenario, "local-retry-backoff"))
    {
        builtin_pcm_sink.ops.play(audio, sizeof(audio));
        long long start = now_ms();
        delay_ms(1900);
        unsigned int automatic = __atomic_load_n(&spawn_attempts, __ATOMIC_RELAXED);
        assert(automatic >= 1 && automatic <= 4);
        sink_lock();
        assert(playing && active_helper.descriptor < 0 && source_size == sizeof(audio));
        assert(last_error == -ENODEV);
        sink_unlock();
        printf("{\"automatic_launches\":%u,\"interval_ms\":%lld", automatic, now_ms() - start);
        start = now_ms();
        assert(pcm_alsa_switch_playback_device(LOCAL_DEVICE) == -ENODEV);
        assert(now_ms() - start < 700);
        unsigned int explicit_launches = __atomic_load_n(&spawn_attempts, __ATOMIC_RELAXED);
        assert(explicit_launches > automatic);
        sink_lock();
        unsigned int before = __atomic_load_n(&spawn_attempts, __ATOMIC_RELAXED);
        builtin_pcm_sink.ops.set_freq(1);
        sink_unlock();
        long long deadline = now_ms() + 700;
        while (__atomic_load_n(&spawn_attempts, __ATOMIC_RELAXED) == before && now_ms() < deadline) delay_ms(2);
        unsigned int rate_launches = __atomic_load_n(&spawn_attempts, __ATOMIC_RELAXED);
        assert(rate_launches > before);
        delay_ms(50);
        before = __atomic_load_n(&spawn_attempts, __ATOMIC_RELAXED);
        builtin_pcm_sink.ops.play(audio, sizeof(audio));
        deadline = now_ms() + 700;
        while (__atomic_load_n(&spawn_attempts, __ATOMIC_RELAXED) == before && now_ms() < deadline) delay_ms(2);
        unsigned int play_launches = __atomic_load_n(&spawn_attempts, __ATOMIC_RELAXED);
        assert(play_launches > before);
        printf(",\"explicit_launches\":%u,\"rate_launches\":%u,\"play_launches\":%u}\n",
               explicit_launches, rate_launches, play_launches);
        start = now_ms();
        hiby_pcm_shutdown();
        assert(now_ms() - start < 700);
        verify_reaped();
        return 0;
    }
    assert(wait_output(false, 1500));
#ifdef PCM_TEST_STACK_MIN
    assert(initialized && requested_stack_size >= PTHREAD_STACK_MIN && requested_stack_size >= 65536);
#endif
    builtin_pcm_sink.ops.postinit();
    pcm_alsa_set_bluetooth_volume(0, -60);
    if (!strcmp(scenario, "shutdown-concurrent") || !strcmp(scenario, "shutdown-reinitialize"))
    {
        bool initialize = !strcmp(scenario, "shutdown-reinitialize");
        pthread_mutex_lock(&shutdown_gate_mutex);
        join_gate_hold = true;
        pthread_mutex_unlock(&shutdown_gate_mutex);
        pthread_t first, second;
        assert(!pthread_create(&first, NULL, shutdown_thread, NULL));
        wait_shutdown_gate(false);
        assert(!pthread_create(&second, NULL, initialize ? initialization_thread : shutdown_thread, NULL));
        delay_ms(40);
        assert(__atomic_load_n(&shutdown_returns, __ATOMIC_ACQUIRE) == 0);
        assert(__atomic_load_n(&initialization_returns, __ATOMIC_ACQUIRE) == 0);
        pthread_mutex_lock(&shutdown_gate_mutex);
        join_gate_hold = false;
        pthread_cond_broadcast(&shutdown_gate_changed);
        pthread_mutex_unlock(&shutdown_gate_mutex);
        assert(!pthread_join(first, NULL));
        assert(!pthread_join(second, NULL));
        assert(__atomic_load_n(&shutdown_returns, __ATOMIC_ACQUIRE) == (initialize ? 1u : 2u));
        if (!initialize)
        {
            verify_reaped();
            builtin_pcm_sink.ops.init();
        }
        else
            assert(__atomic_load_n(&initialization_returns, __ATOMIC_ACQUIRE) == 1);
        assert(wait_output(false, 1500));
    }
    else if (!strcmp(scenario, "shutdown-route-candidate"))
    {
        pthread_mutex_lock(&shutdown_gate_mutex);
        route_gate_hold = true;
        pthread_mutex_unlock(&shutdown_gate_mutex);
        unsigned int before = __atomic_load_n(&spawn_attempts, __ATOMIC_RELAXED);
        pthread_t route, shutdown;
        assert(!pthread_create(&route, NULL, route_thread, NULL));
        long long deadline = now_ms() + 700;
        while (__atomic_load_n(&spawn_attempts, __ATOMIC_RELAXED) == before)
        {
            assert(now_ms() < deadline);
            delay_ms(2);
        }
        assert(!pthread_create(&shutdown, NULL, shutdown_thread, NULL));
        wait_shutdown_gate(true);
        delay_ms(40);
        assert(__atomic_load_n(&shutdown_returns, __ATOMIC_ACQUIRE) == 0);
        pthread_mutex_lock(&shutdown_gate_mutex);
        route_gate_hold = false;
        pthread_cond_broadcast(&shutdown_gate_changed);
        pthread_mutex_unlock(&shutdown_gate_mutex);
        assert(!pthread_join(route, NULL));
        assert(!pthread_join(shutdown, NULL));
        assert(route_result == -ECANCELED);
        verify_reaped();
        builtin_pcm_sink.ops.init();
        assert(wait_output(false, 1500));
    }
    else if (!strcmp(scenario, "route-cancel") || !strcmp(scenario, "route-busy"))
    {
        pthread_t worker;
        assert(!pthread_create(&worker, NULL, route_thread, NULL));
        delay_ms(35);
        long long start = now_ms();
        assert(pcm_alsa_switch_playback_device(bt_device) == -EBUSY);
        assert(now_ms() - start < 60);
        __atomic_store_n(&cancel_route, true, __ATOMIC_RELEASE);
        assert(!pthread_join(worker, NULL));
        assert(route_result == -ECANCELED && wait_output(false, 100));
    }
    else if (!strcmp(scenario, "route-fail") || !strcmp(scenario, "route-timeout"))
    {
        long long start = now_ms();
        int result = pcm_alsa_switch_playback_device(bt_device);
        assert(result < 0 && (strcmp(scenario, "route-timeout") || result == -ETIMEDOUT));
        assert(now_ms() - start < 700 && wait_output(false, 100));
    }
    else if (!strcmp(scenario, "same-route"))
    {
        assert(!pcm_alsa_switch_playback_device(LOCAL_DEVICE));
        assert(!pcm_alsa_switch_playback_device(bt_device));
        assert(!pcm_alsa_switch_playback_device(bt_device));
        __atomic_store_n(&cancel_route, true, __ATOMIC_RELEASE);
        assert(pcm_alsa_switch_playback_device_cancellable(bt_device, cancelled, NULL) == -ECANCELED);
    }
    else if (!strcmp(scenario, "stop-tail"))
    {
        assert(!pcm_alsa_switch_playback_device(bt_device));
        builtin_pcm_sink.ops.play(audio, sizeof(audio));
        long long deadline = now_ms() + 250;
        bool tail = false;
        while (now_ms() < deadline)
        {
            sink_lock();
            tail = !playing && stop_pending;
            sink_unlock();
            if (tail) break;
            delay_ms(2);
        }
        assert(tail);
        delay_ms(20);
        long long start = now_ms();
        builtin_pcm_sink.ops.stop();
        assert(now_ms() - start < 60);
        wait_end(250);
        sink_lock();
        assert(last_error == 0);
        sink_unlock();
    }
    else if (!strcmp(scenario, "finite-pool"))
    {
        __atomic_store_n(&hold_reaping, true, __ATOMIC_RELEASE);
        struct helper_process candidates[PCM_PROCESS_SLOTS];
        for (int position = 0; position < PCM_PROCESS_SLOTS - 1; position++)
            assert(open_helper(bt_device, 44100, &candidates[position], NULL, NULL) == -ETIMEDOUT);
        long long start = now_ms();
        assert(open_helper(bt_device, 44100, &candidates[PCM_PROCESS_SLOTS - 1], NULL, NULL) == -EBUSY);
        assert(now_ms() - start < 60);
        __atomic_store_n(&hold_reaping, false, __ATOMIC_RELEASE);
    }
    else if (!strcmp(scenario, "route-churn"))
    {
        for (unsigned int iteration = 0; iteration < 20; iteration++)
        {
            int result;
            do { result = pcm_alsa_switch_playback_device(bt_device); delay_ms(2); } while (result == -EBUSY);
            assert(!result && pcm_alsa_bluetooth_active());
            builtin_pcm_sink.ops.set_freq((uint16_t)(iteration % 2));
            assert(wait_output(true, 1500));
            do { result = pcm_alsa_switch_playback_device(LOCAL_DEVICE); delay_ms(2); } while (result == -EBUSY);
            assert(!result && !pcm_alsa_bluetooth_active());
        }
    }
    else if (!strcmp(scenario, "stop-restart"))
    {
        assert(!pcm_alsa_switch_playback_device(bt_device));
        for (unsigned int iteration = 0; iteration < 20; iteration++)
        {
            builtin_pcm_sink.ops.play(audio, sizeof(audio));
            delay_ms(2);
            long long start = now_ms();
            builtin_pcm_sink.ops.stop();
            assert(now_ms() - start < 60);
        }
        wait_end(1200);
    }
    else if (!strcmp(scenario, "removed-idle"))
    {
        assert(!pcm_alsa_switch_playback_device(bt_device));
        assert(wait_output(false, 1500));
        assert(pcm_alsa_get_xruns() > 0);
    }
    else if (!strcmp(scenario, "helper-killed"))
    {
        assert(!pcm_alsa_switch_playback_device(bt_device));
        sink_lock();
        assert(!kill(active_helper.process, SIGKILL));
        sink_unlock();
        assert(wait_output(false, 1500));
        assert(pcm_alsa_get_xruns() > 0);
    }
    else
    {
#ifdef FAKE_ALSA
        if (strcmp(scenario, "stack-minimum"))
            assert(!pcm_alsa_switch_playback_device(bt_device));
#endif
        if (!strcmp(scenario, "invalid-more")) invalid_more = true;
        builtin_pcm_sink.ops.play(audio, sizeof(audio));
        if (!strcmp(scenario, "ack-clock"))
        {
            delay_ms(40);
            sink_lock();
            assert(more_calls == 0 && inflight && source_size == 4096);
            sink_unlock();
        }
        if (!strcmp(scenario, "fallback"))
        {
            assert(wait_output(false, 1500));
            assert(pcm_alsa_get_xruns() > 0);
        }
        if (!strcmp(scenario, "invalid-more"))
        {
            delay_ms(150);
            sink_lock();
            assert(!playing && last_error == -EINVAL && status_calls > 0);
            sink_unlock();
        }
        else wait_end(2500);
        if (!strcmp(scenario, "stream") || !strcmp(scenario, "closed-fds") ||
            !strcmp(scenario, "stack-minimum"))
        {
            sink_lock();
            assert(more_calls == 1 && last_error == 0);
            sink_unlock();
        }
    }
    long long start = now_ms();
    hiby_pcm_shutdown();
    assert(now_ms() - start < 700);
    hiby_pcm_shutdown();
    verify_reaped();
    if (!strcmp(scenario, "reinitialize"))
    {
        pcm_alsa_set_playback_device(LOCAL_DEVICE);
        builtin_pcm_sink.ops.init();
        assert(wait_output(false, 1500));
        hiby_pcm_shutdown();
        verify_reaped();
    }
    return 0;
}
'''

MIXER_PREAMBLE = r'''
#define MIX_FRAME_SAMPLES 1024
#define IBSS_ATTR
#define DOWNMIX_BUF_IBSS
#define MEM_ALIGN_ATTR
#define MIXER_CALLBACK_ICODE
#define FORCE_INLINE inline
#define LIKELY(value) (value)
#define UNLIKELY(value) (value)
#define MIN(first, second) ((first) < (second) ? (first) : (second))
#define MIX_AMP_UNITY 0x10000
#define MIX_AMP_MUTE 0
#define ALIGN_AUDIOBUF(start, size) do { \
    (start) = (void *)(((uintptr_t)(start) + 3) & ~(uintptr_t)3); \
    (size) &= ~(size_t)3; } while (0)
#define logf(...) ((void)0)
#define mixer_buffer_callback_exit() ((void)0)
typedef void (*pcm_play_callback_type)(const void **, size_t *);
typedef enum pcm_dma_status (*pcm_status_callback_type)(enum pcm_dma_status);
volatile pcm_play_callback_type pcm_callback_for_more;
volatile pcm_status_callback_type pcm_play_status_callback;
static volatile bool pcm_playing;
static void pcm_play_lock(void) { sink_lock(); }
static void pcm_play_unlock(void) { sink_unlock(); }
static unsigned int pcm_get_frequency(void) { return pcm_alsa_get_rate(); }
static void pcm_apply_settings(void) {}
static void pcm_play_dma_start_int(const void *address, size_t size) { sink_play(address, size); }
static void pcm_play_dma_stop_int(void) { sink_stop(); }
static int16_t clip_sample_16(int32_t value)
{
    return (int16_t)(value < INT16_MIN ? INT16_MIN : value > INT16_MAX ? INT16_MAX : value);
}
void pcm_play_stop_int(void);
static enum pcm_dma_status mixer_buffer_callback(enum pcm_dma_status status);
void audiohw_preinit(void) {}
void audiohw_postinit(void) {}
'''

MIXER_MAIN = r'''
int main(int argc, char **argv)
{
    int helper = hiby_pcm_helper_main(argc, argv);
    if (helper >= 0) return helper;
    assert(argc == 2);
    static int16_t music[8192 * 2], voice[4096 * 2];
    for (size_t position = 0; position < sizeof(music) / sizeof(music[0]); position++) music[position] = 16000;
    for (size_t position = 0; position < sizeof(voice) / sizeof(voice[0]); position++) voice[position] = 4000;
    builtin_pcm_sink.ops.init();
    assert(wait_output(false, 1500));
    assert(!pcm_alsa_switch_playback_device(bt_device));
    pcm_alsa_set_bluetooth_volume(0, 0);
    sink_lock();
    bool send_fatal = !strcmp(argv[1], "mixer-send-fatal");
    bool send_again = !strcmp(argv[1], "mixer-send-again");
    if (send_fatal || send_again) fail_next_data_errno = send_fatal ? EPIPE : EAGAIN;
    mixer_channel_set_amplitude(PCM_MIXER_CHAN_PLAYBACK, MIX_AMP_UNITY / 4);
    mixer_channel_set_amplitude(PCM_MIXER_CHAN_VOICE, MIX_AMP_UNITY);
    mixer_channel_play_data(PCM_MIXER_CHAN_PLAYBACK, NULL, music, sizeof(music));
    mixer_channel_play_data(PCM_MIXER_CHAN_VOICE, NULL, voice, sizeof(voice));
    sink_unlock();
    wait_end(3000);
    sink_lock();
    assert(!pcm_is_playing());
    assert(mixer_channel_status(PCM_MIXER_CHAN_PLAYBACK) == CHANNEL_STOPPED);
    assert(mixer_channel_status(PCM_MIXER_CHAN_VOICE) == CHANNEL_STOPPED);
    if (send_fatal || send_again)
    {
        assert(data_send_failures == 1 && fail_next_data_errno == 0);
        assert(!pcm_callback_for_more && !pcm_play_status_callback);
        assert(!playing);
        assert(send_fatal ? pcm_alsa_get_xruns() > 0 : pcm_alsa_get_xruns() == 0);
        assert(pcm_alsa_bluetooth_active() == !send_fatal);
        mixer_channel_play_data(PCM_MIXER_CHAN_PLAYBACK, NULL, music, sizeof(music));
        mixer_channel_play_data(PCM_MIXER_CHAN_VOICE, NULL, voice, sizeof(voice));
        assert(pcm_is_playing() && playing);
    }
    sink_unlock();
    if (send_fatal || send_again)
    {
        wait_end(3000);
        sink_lock();
        assert(!pcm_is_playing() && !playing);
        assert(mixer_channel_status(PCM_MIXER_CHAN_PLAYBACK) == CHANNEL_STOPPED);
        assert(mixer_channel_status(PCM_MIXER_CHAN_VOICE) == CHANNEL_STOPPED);
        assert(!pcm_callback_for_more && !pcm_play_status_callback);
        sink_unlock();
    }
    hiby_pcm_shutdown();
    verify_reaped();
    return 0;
}
'''


def actual_mixer_program():
    inputs = {name: (ROOT / name).read_text(encoding="utf-8") for name in MIXER_INPUTS}
    mixer = inputs["firmware/pcm_mixer.c"]
    header = inputs["firmware/export/pcm_mixer.h"]
    internal = inputs["firmware/export/pcm-internal.h"]
    pieces = [MIXER_PREAMBLE]
    for signature in ("enum pcm_mixer_channel", "enum channel_status", "struct mixer_play_cbs", "struct mixer_buffer_cbs"):
        pieces.append(extract_block(header, signature) + ";\n")
    pieces.extend(function(internal, name).replace("static FORCE_INLINE", "") if name == "pcm_play_dma_status_callback"
                  else function(internal, name) for name in ("pcm_get_more_int", "pcm_call_status_cb", "pcm_play_call_status_cb", "pcm_play_dma_status_callback"))
    pieces.extend(function(inputs["firmware/pcm.c"], name) for name in ("pcm_play_stop_int", "pcm_play_dma_complete_callback", "pcm_is_playing", "pcm_play_data"))
    pieces.append(mixer[mixer.index("static unsigned int mix_frame_size"):mixer.index("static inline unsigned int max_idle_frames")])
    pieces.append(function(mixer, "max_idle_frames"))
    pieces.extend(function(inputs["firmware/asm/pcm-mixer.c"], name) for name in ("mix_samples", "write_samples"))
    pieces.extend(function(inputs["firmware/general.c"], name) for name in ("find_array_ptr", "remove_array_ptr"))
    pieces.extend(function(mixer, name) for name in ("mixer_activate_channel", "mixer_deactivate_channel", "channel_stopped",
                  "mixer_pcm_callback", "chan_call_buffer_hook", "mixer_buffer_callback", "mixer_start_pcm", "mixer_channel_play_data", "mixer_channel_set_amplitude", "mixer_channel_status"))
    middle_start = PROGRAM.index("void audiohw_preinit(void) {}")
    middle_end = PROGRAM.index("static bool cancelled(void *context)", middle_start)
    program = PROGRAM[:middle_start] + "\n".join(pieces) + PROGRAM[middle_end:]
    return program[:program.index("int main(int argc, char **argv)")] + MIXER_MAIN


@unittest.skipUnless(sys.platform.startswith("linux") and hasattr(os, "P_PIDFD") and hasattr(os, "pidfd_open") and
                     hasattr(signal, "pidfd_send_signal") and shutil.which("gcc"),
                     "requires Linux pidfd/session isolation, a compiler and ALSA development headers")
class PcmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.evidence = project_materials_root(ROOT) / "r1-gesture-extensions-20261016/pcm-timeout/pcm-cases" / (stamp + "-" + uuid.uuid4().hex[:8])
        cls.evidence.mkdir(parents=True)
        cls.commands = []
        cls.outcomes = []
        cls.cases = []
        cls.source_paths = (SOURCE, HEADER, Path(__file__), *(ROOT / name for name in MIXER_INPUTS), ROOT / "apps/main.c", ROOT / "firmware/SOURCES")
        cls.source_hashes = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in cls.source_paths}
        (cls.evidence / "hiby-pcm-test.h").write_text(SHIM, encoding="utf-8")
        program = cls.evidence / "pcm-test.c"
        program.write_text(PROGRAM.replace("SOURCE_PATH", SOURCE.as_posix()), encoding="utf-8")
        cls.flags = ["gcc", "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-Wformat=2", "-Wshadow", "-Wconversion",
                     "-O1", "-g", "-pthread", "-DHIBY_PCM_HOST_TEST", "-DHIBY_PCM_OPEN_TIMEOUT_MS=250",
                     "-DHIBY_PCM_STALL_TIMEOUT_MS=350", "-DHIBY_PCM_HEARTBEAT_MS=100", "-I", str(cls.evidence), "-I", str(HEADER.parent), str(program)]
        cls.binary = cls.evidence / "pcm-fake"
        cls.real = cls.evidence / "pcm-real"
        cls.sanitized = cls.evidence / "pcm-sanitized"
        cls.compile_command(cls.flags + ["-DFAKE_ALSA", "-lm", "-o", str(cls.binary)])
        cls.compile_command(cls.flags + ["-lasound", "-lm", "-o", str(cls.real)])
        cls.compile_command(cls.flags + ["-DFAKE_ALSA", "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                                        "-fno-omit-frame-pointer", "-lm", "-o", str(cls.sanitized)])
        mixed = cls.evidence / "pcm-mixer-test.c"
        mixed.write_text(actual_mixer_program().replace("SOURCE_PATH", SOURCE.as_posix()), encoding="utf-8")
        cls.mixed = cls.evidence / "pcm-mixer-test"
        mixed_flags = [str(mixed) if argument == str(program) else argument for argument in cls.flags]
        cls.compile_command(mixed_flags + ["-DFAKE_ALSA", "-Wno-conversion", "-Wno-shadow", "-Wno-unused-variable", "-Wno-unused-function",
                                          "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer", "-lm", "-o", str(cls.mixed)])

    @classmethod
    def compile_command(cls, arguments):
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=90)
        cls.commands.append({"arguments": arguments, "returncode": result.returncode,
                             "stdout": result.stdout, "stderr": result.stderr})
        if result.returncode:
            (cls.evidence / "build-failure.json").write_text(json.dumps(cls.commands, indent=2), encoding="utf-8")
            raise RuntimeError(result.stderr)

    def run_case(self, scenario, mode="good", binary=None):
        log = self.evidence / (self._testMethodName + "-" + mode + "-" + uuid.uuid4().hex[:8] + ".pcm")
        environment = dict(os.environ, PCM_MODE=mode, PCM_LOG=str(log),
                           ASAN_OPTIONS="detect_leaks=1:abort_on_error=1:log_path=" + str(log) + ".asan",
                           UBSAN_OPTIONS="halt_on_error=1:log_path=" + str(log) + ".ubsan")
        command = [str(binary or self.binary), scenario]
        outcome = {"test": self.id(), "scenario": scenario, "mode": mode, "arguments": command, "log": str(log)}
        self.outcomes.append(outcome)
        result = run_isolated_case(command, environment, record=outcome, cwd=self.evidence)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        self.assertEqual(list(self.evidence.glob(log.name + ".asan*")), [])
        self.assertEqual(list(self.evidence.glob(log.name + ".ubsan*")), [])
        records = []
        if log.exists():
            raw = log.read_bytes()
            position = 0
            while position < len(raw):
                event, bluetooth, length = struct.unpack_from("=III", raw, position)
                position += 12
                self.assertLessEqual(length, len(raw) - position)
                records.append((event, bluetooth, raw[position:position + length]))
                position += length
        return records

    def tearDown(self):
        result = self._outcome.result
        failed = any(getattr(test, "test_case", test).id() == self.id() for test, _ in result.failures + result.errors)
        self.cases.append({"test": self.id(), "passed": not failed})

    @classmethod
    def tearDownClass(cls):
        after = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in cls.source_paths}
        unchanged = cls.source_hashes == after
        report = {"scope": "Actual HiBy PCM C driver with exec helper, controlled ALSA and host ALSA null; not R1 hardware acceptance",
                  "source_sha256": cls.source_hashes, "source_sha256_after": after, "sources_unchanged": unchanged,
                  "commands": cls.commands, "runs": cls.outcomes, "cases": cls.cases,
                  "passed": unchanged and all(case["passed"] for case in cls.cases)}
        (cls.evidence / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("PCM evidence:", cls.evidence)

    def test_protocol_and_route_validation(self):
        self.run_case("validation")

    def test_target_stack_minimum_starts_pump_and_delivers_every_sample(self):
        for minimum in (16384, 131072):
            with self.subTest(stack_minimum=minimum):
                binary = self.evidence / f"pcm-stack-minimum-{minimum}"
                self.compile_command(self.flags + ["-DFAKE_ALSA", f"-DPCM_TEST_STACK_MIN={minimum}",
                                                   "-lm", "-o", str(binary)])
                records = self.run_case("stack-minimum", binary=binary)
                self.assertTrue(all(not bluetooth for _, bluetooth, _ in records))
                self.assertEqual(sum(event == 1 for event, _, _ in records), 1)
                self.assertEqual([payload for event, _, payload in records if event == 6],
                                 [struct.pack("=I", 44100)])
                self.assertTrue(any(event == 7 for event, _, _ in records))
                data = b"".join(payload for event, _, payload in records if event == 2)
                self.assertEqual(data, struct.pack("=hh", 16000, -16000) * 2048)
                self.assertTrue(any(event == 3 for event, _, _ in records))

    def test_stereo_gain_and_natural_end_drain(self):
        records = self.run_case("stream")
        data = b"".join(payload for event, bluetooth, payload in records if event == 2 and bluetooth)
        self.assertEqual(len(data), 8192)
        samples = struct.unpack("=" + "h" * (len(data) // 2), data)
        self.assertTrue(all(samples[position] == 16000 and -8050 < samples[position + 1] < -7950
                            for position in range(0, len(samples), 2)))
        self.assertTrue(any(event == 3 and bluetooth for event, bluetooth, _ in records))

    def test_partial_writes_preserve_every_sample(self):
        records = self.run_case("stream", "partial")
        data = b"".join(payload for event, bluetooth, payload in records if event == 2 and bluetooth)
        self.assertEqual(len(data), 8192)
        self.assertGreater(sum(event == 2 and bluetooth for event, bluetooth, _ in records), 2)

    def test_xrun_and_suspend_recovery(self):
        for mode, expected in (("xrun", 7), ("suspend", 8)):
            with self.subTest(mode=mode):
                records = self.run_case("stream", mode)
                self.assertEqual(sum(len(data) for event, bt, data in records if event == 2 and bt), 8192)
                self.assertTrue(any(event == expected and bt for event, bt, _ in records))

    def test_open_and_configuration_failure_preserve_wired(self):
        for mode in ("open-fail", "config-fail"):
            with self.subTest(mode=mode):
                self.run_case("route-fail", mode)

    def test_open_configuration_hangs_are_bounded(self):
        for mode in ("open-hang", "config-hang"):
            with self.subTest(mode=mode):
                self.run_case("route-timeout", mode)

    def test_cancellable_route_and_serialized_busy(self):
        self.run_case("route-cancel", "open-hang")

    def test_data_acknowledgement_gates_core_callback_clock(self):
        self.run_case("ack-clock", "write-delay")

    def test_idempotent_route_does_not_open_exclusive_device_twice(self):
        records = self.run_case("same-route")
        self.assertEqual(sum(event == 1 and not bluetooth for event, bluetooth, _ in records), 1)
        self.assertEqual(sum(event == 1 and bluetooth for event, bluetooth, _ in records), 1)

    def test_explicit_stop_cancels_nonblocking_tail_drain(self):
        records = self.run_case("stop-tail", "drain-again")
        self.assertTrue(any(event == 3 and bluetooth for event, bluetooth, _ in records))
        self.assertTrue(any(event == 4 and bluetooth for event, bluetooth, _ in records))

    def test_write_hang_error_and_heartbeat_without_progress_fall_back(self):
        for mode in ("write-hang", "write-error", "write-again"):
            with self.subTest(mode=mode):
                self.run_case("fallback", mode)

    def test_idle_disconnection_detected(self):
        self.run_case("removed-idle", "removed-idle")

    def test_shutdown_callers_wait_until_owned_worker_cleanup_completes(self):
        for binary in (self.binary, self.sanitized):
            self.run_case("shutdown-concurrent", binary=binary)

    def test_shutdown_waits_for_cancelled_external_route_candidate_cleanup(self):
        for binary in (self.binary, self.sanitized):
            self.run_case("shutdown-route-candidate", "open-hang", binary)

    def test_reinitialization_waits_for_shutdown_before_creating_fresh_worker(self):
        for binary in (self.binary, self.sanitized):
            self.run_case("shutdown-reinitialize", binary=binary)

    def test_external_helper_death_falls_back_without_panic(self):
        self.run_case("helper-killed")

    def test_hanging_drain_and_close_never_block_shutdown(self):
        self.run_case("fallback", "drain-hang")
        self.run_case("stream", "close-hang")

    def test_finite_unreaped_child_budget(self):
        self.run_case("finite-pool", "open-hang")

    def test_stop_restart_flush_is_nonblocking(self):
        self.run_case("stop-restart", "partial")

    def test_route_churn_and_frequency_changes(self):
        self.run_case("route-churn")

    def test_null_or_empty_core_buffer_is_rejected(self):
        self.run_case("invalid-more")

    def test_closed_standard_descriptors_and_reinitialize(self):
        self.run_case("closed-fds")
        self.run_case("reinitialize")

    def test_actual_alsa_null_exec_helper(self):
        self.run_case("stream", binary=self.real)

    def test_actual_core_mixer_music_voice_and_ducking_gain_share_helper(self):
        records = self.run_case("mixer", binary=self.mixed)
        data = b"".join(payload for event, bluetooth, payload in records if event == 2 and bluetooth)
        samples = struct.unpack("=" + "h" * (len(data) // 2), data)
        self.assertEqual(samples.count(8000), 4096 * 2)
        self.assertEqual(samples.count(4000), 4096 * 2)
        self.assertTrue(all(sample in (0, 4000, 8000) for sample in samples))

    def test_actual_core_data_send_fatal_preserves_chunk_and_restarts_music_voice(self):
        records = self.run_case("mixer-send-fatal", binary=self.mixed)
        data = b"".join(payload for event, _, payload in records if event == 2)
        samples = struct.unpack("=" + "h" * (len(data) // 2), data)
        self.assertEqual(samples.count(8000), 2 * 4096 * 2)
        self.assertEqual(samples.count(4000), 2 * 4096 * 2)
        self.assertTrue(all(sample in (0, 4000, 8000) for sample in samples))
        self.assertEqual(sum(len(payload) for event, bluetooth, payload in records if event == 2 and bluetooth), 0)

    def test_actual_core_data_send_again_keeps_route_and_samples(self):
        records = self.run_case("mixer-send-again", binary=self.mixed)
        data = b"".join(payload for event, bluetooth, payload in records if event == 2 and bluetooth)
        samples = struct.unpack("=" + "h" * (len(data) // 2), data)
        self.assertEqual(samples.count(8000), 2 * 4096 * 2)
        self.assertEqual(samples.count(4000), 2 * 4096 * 2)

    def test_persistent_local_failure_has_backoff_and_explicit_retry_resets(self):
        records = self.run_case("local-retry-backoff", "local-open-fail")
        self.assertTrue(all(not bluetooth for event, bluetooth, _ in records if event == 1))
        self.assertGreaterEqual(sum(event == 1 for event, _, _ in records), 4)

    def test_actual_helper_rejects_wrong_shape_and_descriptor(self):
        for arguments, status in ((["invalid", "44100", "3"], 64),
                                  (["null", "44100", "5"], 64),
                                  (["null", "44100x", "3"], 64),
                                  (["null", "0", "3"], 64),
                                  (["null", "44100", "3"], 65)):
            result = subprocess.run([str(self.real), "--hiby-pcm-helper"] + arguments, timeout=2, capture_output=True)
            self.assertEqual(result.returncode, status)

    def test_helper_protocol_failure_and_eof_cleanup(self):
        self.run_case("helper-protocol", binary=self.real)
        self.run_case("helper-eof", binary=self.real)

    def test_address_and_undefined_sanitizers(self):
        for scenario, mode in (("stream", "partial"), ("route-cancel", "open-hang"),
                               ("fallback", "write-again"), ("stop-restart", "partial"), ("validation", "good")):
            with self.subTest(scenario=scenario):
                self.run_case(scenario, mode, self.sanitized)

    def test_actual_mips_driver_compiles(self):
        central = project_materials_root(ROOT)
        native = central / "toolchains/hiby-r1-20261010/prefix/bin/mipsel-rockbox-linux-gnu-gcc"
        if not native.is_file():
            self.skipTest("actual R1 toolchain unavailable")
        shared = ["firmware", "firmware/export", "firmware/drivers", "firmware/include", "firmware/kernel/include",
                  "firmware/target/hosted/hiby/r1", "firmware/target/hosted/hiby", "firmware/target/hosted",
                  "lib/rbcodec", "lib/rbcodec/codecs", "lib/rbcodec/dsp", "lib/fixedpoint"]
        arguments = [str(native), "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-Wformat=2", "-Wno-pointer-sign",
                     "-DROCKBOX", "-DMEMORYSIZE=16", "-DHIBY_R1", "-DTARGET_ID=124", "-DAPPLICATION", "-D_GNU_SOURCE=1",
                     "-march=mips32r2", "-mhard-float", "-I", str(central / "build-espeak-hibyr1")]
        for directory in shared:
            arguments += ["-I", str(ROOT / directory)]
        self.compile_command(arguments + ["-c", str(SOURCE), "-o", str(self.evidence / "pcm-native.o")])

    def test_source_selection_does_not_replace_siblings_or_simulator(self):
        source = ROOT / "firmware/SOURCES"
        scenarios = [(["HIBY_LINUX", "HIBY_R1", "HAVE_ESPEAK"], "pcm-hiby.c"),
                     (["HIBY_LINUX", "HIBY_R1"], "pcm-alsa.c"),
                     (["HIBY_LINUX", "HAVE_ESPEAK"], "pcm-alsa.c"),
                     (["FIIO_M3K_LINUX", "HAVE_ESPEAK"], "pcm-alsa.c"),
                     (["SONY_NWZ_LINUX", "HAVE_ESPEAK"], "pcm-alsa.c"),
                     (["HIBY_LINUX", "HIBY_R1", "HAVE_ESPEAK", "SIMULATOR"], None),
                     (["HIBY_LINUX", "HIBY_R1", "HAVE_ESPEAK", "BOOTLOADER"], None)]
        for definitions, expected in scenarios:
            with self.subTest(definitions=definitions):
                command = ["gcc", "-E", "-P", "-x", "c"] + ["-D" + value for value in definitions] + [str(source)]
                result = subprocess.run(command, text=True, capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                actual = [line.strip() for line in result.stdout.splitlines() if line.strip().endswith(("/pcm-hiby.c", "/pcm-alsa.c"))]
                self.assertEqual(actual, [] if expected is None else ["target/hosted/" + ("hiby/" if expected == "pcm-hiby.c" else "") + expected])

    def test_native_helper_returns_before_main_initialization(self):
        main = (ROOT / "apps/main.c").read_text(encoding="utf-8")
        start = main.index("#ifdef HAVE_ARGV_MAIN\nint main(")
        end = main.index('    CHART(">init");', start)
        prefix = main[start:end]
        self.assertNotIn("init();", prefix)
        self.assertLess(prefix.index("return helper_result;"), len(prefix))
        test = self.evidence / "early-main.c"
        test.write_text("#define INIT_ATTR\n#define MAIN_NORETURN_ATTR\n#define HAVE_ARGV_MAIN\n"
                        "int hiby_pcm_helper_main(int count, char **arguments) { (void)arguments; return count > 1 ? 23 : -1; }\n"
                        "void sys_handle_argv(int count, char **arguments) { (void)count; (void)arguments; }\n" + prefix + "return 31; }\n",
                        encoding="utf-8")
        for definitions, expected in ((["HIBY_R1", "HAVE_ESPEAK"], 23),
                                      (["HIBY_R1", "HAVE_ESPEAK", "SIMULATOR"], 31),
                                      (["HIBY_R1", "HAVE_ESPEAK", "BOOTLOADER"], 31),
                                      (["HIBY_R1"], 31), (["HAVE_ESPEAK"], 31)):
            with self.subTest(definitions=definitions):
                binary = self.evidence / ("early-main-" + "-".join(definitions))
                self.compile_command(["gcc", "-Wall", "-Wextra", "-Werror"] + ["-D" + value for value in definitions] + [str(test), "-o", str(binary)])
                self.assertEqual(subprocess.run([str(binary), "helper"], timeout=2).returncode, expected)
                self.assertEqual(subprocess.run([str(binary)], timeout=2).returncode, 31)


@unittest.skipUnless(sys.platform.startswith("linux") and hasattr(os, "P_PIDFD") and hasattr(os, "pidfd_open") and
                     hasattr(signal, "pidfd_send_signal") and shutil.which("gcc"),
                     "requires Linux pidfd/session isolation, a compiler and ALSA development headers")
class PcmRouteRaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.evidence = project_materials_root(ROOT) / "hiby-pcm-route-race-tests" / (stamp + "-" + uuid.uuid4().hex[:8])
        cls.evidence.mkdir(parents=True, exist_ok=False)
        cls.commands, cls.outcomes, cls.cases = [], [], []
        cls.source_paths = (SOURCE, HEADER, Path(__file__), RACE_FIXTURE)
        cls.source_hashes = cls.input_hashes()
        cls.binaries = {}
        cls.addClassCleanup(cls.write_report)
        (cls.evidence / "hiby-pcm-test.h").write_text(SHIM, encoding="utf-8")
        source = SOURCE.read_text(encoding="utf-8")
        guard = "if (!explicit_request && route_intent_generation != recovery_generation)"
        increment = "route_intent_generation++;"
        fallback = "switch_playback_device(LOCAL_DEVICE, shutdown_requested, NULL, false, recovery_generation)"
        variants = {
            "root": None,
            "removed-guard": cls.replace_once(source, guard, "if (false && !explicit_request && route_intent_generation != recovery_generation)"),
            "epoch-only": cls.replace_once(cls.replace_once(source, guard,
                "if (false && !explicit_request && route_intent_generation != recovery_generation)"), increment, "epoch++;"),
            "missing-increment": cls.replace_once(source, increment, "route_intent_generation += 0;"),
            "refreshed-fallback": cls.replace_once(source, fallback,
                "switch_playback_device(LOCAL_DEVICE, shutdown_requested, NULL, false, route_intent_generation)"),
        }
        prefix = PROGRAM[:PROGRAM.index("int main(int argc, char **argv)")]
        marker = '#include "SOURCE_PATH"'
        declarations = ("static int race_mutex_trylock(pthread_mutex_t *mutex);\n"
                        "static int race_mutex_unlock(pthread_mutex_t *mutex);\n"
                        "#define pthread_mutex_trylock race_mutex_trylock\n"
                        "#define pthread_mutex_unlock race_mutex_unlock\n")
        prefix = cls.replace_once(prefix, marker, declarations + marker +
                                  "\n#undef pthread_mutex_trylock\n#undef pthread_mutex_unlock\n")
        fixture = RACE_FIXTURE.read_text(encoding="utf-8")
        for variant, contents in variants.items():
            selected = SOURCE
            if contents is not None:
                selected = cls.evidence / (variant + ".c")
                selected.write_text(contents, encoding="utf-8")
            program = cls.evidence / (variant + "-race.c")
            program.write_text(prefix.replace("SOURCE_PATH", selected.as_posix()) + fixture, encoding="utf-8")
            for sanitized in (False, True):
                binary = cls.evidence / (variant + ("-asan-ubsan" if sanitized else "-normal"))
                arguments = ["gcc", "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-Wformat=2", "-Wshadow", "-Wconversion",
                             "-Wno-unused-function", "-Wno-unused-variable", "-O1", "-g", "-pthread", "-UNDEBUG",
                             "-DHIBY_PCM_HOST_TEST", "-DFAKE_ALSA", "-DHIBY_PCM_OPEN_TIMEOUT_MS=250",
                             "-DHIBY_PCM_STALL_TIMEOUT_MS=350", "-DHIBY_PCM_HEARTBEAT_MS=100",
                             "-I", str(cls.evidence), "-I", str(HEADER.parent), str(program), "-lm", "-o", str(binary)]
                if sanitized:
                    arguments += ["-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer"]
                result = subprocess.run(arguments, capture_output=True, text=True, timeout=90)
                cls.commands.append(dict(arguments=arguments, returncode=result.returncode,
                                         stdout=result.stdout, stderr=result.stderr))
                if result.returncode:
                    raise RuntimeError(result.stderr)
                cls.binaries[variant, sanitized] = binary

    @staticmethod
    def replace_once(source, old, new):
        if source.count(old) != 1:
            raise AssertionError("PCM race mutation/inclusion point changed: " + old)
        return source.replace(old, new, 1)

    @classmethod
    def input_hashes(cls):
        return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in cls.source_paths}

    @classmethod
    def write_report(cls):
        after = cls.input_hashes()
        passed = (cls.source_hashes == after and bool(cls.cases) and bool(cls.outcomes) and
                  all(case["passed"] for case in cls.cases) and all(run.get("passed") for run in cls.outcomes) and
                  all(command["returncode"] == 0 for command in cls.commands))
        report = dict(scope="Actual ROOT HiBy PCM driver; deterministic route-lock barriers; controlled ALSA only",
                      limitations="No host audio/null execution, Bluetooth, hardware, GUI or native product build",
                      source_sha256=cls.source_hashes, source_sha256_after=after,
                      sources_unchanged=cls.source_hashes == after, commands=cls.commands,
                      runs=cls.outcomes, cases=cls.cases, passed=passed)
        (cls.evidence / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("PCM route-race evidence:", cls.evidence, flush=True)
        if not passed:
            raise AssertionError("PCM route-race tests failed or changed inputs: " + str(cls.evidence))

    def tearDown(self):
        result = self._outcome.result
        failed = any(getattr(test, "test_case", test).id() == self.id() for test, _ in result.failures + result.errors)
        self.cases.append(dict(test=self.id(), passed=not failed))

    def check_race(self, scenario, variant="root"):
        for sanitized in (False, True):
            with self.subTest(scenario=scenario, variant=variant, sanitized=sanitized):
                binary = self.binaries[variant, sanitized]
                log = self.evidence / (binary.name + "-" + scenario + "-" + uuid.uuid4().hex[:8] + ".pcm")
                environment = dict(os.environ, PCM_MODE="good", PCM_LOG=str(log),
                    ASAN_OPTIONS="detect_leaks=1:abort_on_error=1:log_path=" + str(log) + ".asan",
                    UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1:log_path=" + str(log) + ".ubsan")
                expected = 0 if variant == "root" else 101
                outcome = dict(test=self.id(), scenario=scenario, variant=variant, sanitized=sanitized,
                               arguments=[str(binary), scenario], log=str(log), expected_exit=expected, passed=False)
                self.outcomes.append(outcome)
                result = run_isolated_case(outcome["arguments"], environment, timeout=12, record=outcome, cwd=self.evidence)
                self.assertEqual(result.returncode, expected, outcome)
                self.assertEqual(outcome["cleanup_errors"], [])
                self.assertEqual(outcome["session_cleanup"]["survivors"], [])
                self.assertIn("TRACE shutdown_complete helpers_reaped=1", outcome["stdout"])
                self.assertIn("TRACE explicit_success scenario=" + scenario, outcome["stdout"])
                self.assertEqual(list(self.evidence.glob(log.name + ".asan*")), [])
                self.assertEqual(list(self.evidence.glob(log.name + ".ubsan*")), [])
                self.assertNotIn("AddressSanitizer", outcome["stderr"])
                self.assertNotIn("runtime error:", outcome["stderr"])
                if expected:
                    self.assertEqual(outcome["stderr"],
                        "CHECK_FAILED stale automatic recovery overwrote successful explicit route: " + scenario + "\n")
                    self.assertIn("preserved=0", outcome["stdout"])
                else:
                    self.assertEqual(outcome["stderr"], "")
                    self.assertIn("PASS " + scenario, outcome["stdout"])
                    self.assertIn("preserved=1", outcome["stdout"])
                    raw, opens, position = log.read_bytes(), [], 0
                    while position < len(raw):
                        self.assertGreaterEqual(len(raw) - position, 12)
                        event, bluetooth, length = struct.unpack_from("=III", raw, position)
                        position += 12
                        self.assertLessEqual(length, len(raw) - position)
                        if event == 1:
                            opens.append(bluetooth)
                        position += length
                    outcome["open_routes"] = opens
                    expected_opens = [1, 1] if scenario == "stale-fallback" else [int(scenario == "stale-local")]
                    self.assertEqual(opens, expected_opens, "Stale recovery must not even open a superseded route")
                outcome["passed"] = True

    def test_captured_recovery_preserves_new_explicit_route(self):
        for scenario in ("stale-local", "stale-bluetooth"):
            self.check_race(scenario)

    def test_unchanged_and_same_target_recovery_continue(self):
        for scenario in ("unchanged-local", "same-local"):
            self.check_race(scenario)

    def test_failed_primary_cannot_refresh_stale_fallback_intent(self):
        self.check_race("stale-fallback")

    def test_removed_guard_reproduces_both_overwrites(self):
        for scenario in ("stale-local", "stale-bluetooth"):
            self.check_race(scenario, "removed-guard")

    def test_epoch_only_reproduces_both_overwrites(self):
        for scenario in ("stale-local", "stale-bluetooth"):
            self.check_race(scenario, "epoch-only")

    def test_missing_intent_increment_reproduces_both_overwrites(self):
        for scenario in ("stale-local", "stale-bluetooth"):
            self.check_race(scenario, "missing-increment")

    def test_fallback_must_reuse_captured_generation(self):
        self.check_race("stale-fallback", "refreshed-fallback")


@unittest.skipUnless(sys.platform.startswith("linux") and hasattr(os, "P_PIDFD") and hasattr(os, "pidfd_open") and
                     hasattr(signal, "pidfd_send_signal") and shutil.which("gcc"),
                     "requires Linux pidfd/session isolation, a compiler and ALSA development headers")
class PcmLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.evidence = project_materials_root(ROOT) / "hiby-pcm-lifecycle-tests" / (stamp + "-" + uuid.uuid4().hex[:8])
        cls.evidence.mkdir(parents=True, exist_ok=False)
        cls.commands, cls.outcomes, cls.cases = [], [], []
        cls.source_paths = (SOURCE, HEADER, Path(__file__), LIFECYCLE_FIXTURE)
        cls.source_hashes = cls.input_hashes()
        cls.binaries = {}
        cls.addClassCleanup(cls.write_report)
        (cls.evidence / "hiby-pcm-test.h").write_text(SHIM, encoding="utf-8")
        source = SOURCE.read_text(encoding="utf-8")
        variants = {
            "root": None,
            "realtime-wait": PcmRouteRaceTests.replace_once(PcmRouteRaceTests.replace_once(source,
                "pthread_condattr_setclock(&condition_attributes, CLOCK_MONOTONIC)",
                "pthread_condattr_setclock(&condition_attributes, CLOCK_REALTIME)"),
                "clock_gettime(CLOCK_MONOTONIC, &deadline)", "clock_gettime(CLOCK_REALTIME, &deadline)"),
            "no-idle-reap": PcmRouteRaceTests.replace_once(source,
                "retire_helper(retired);\n        reap_retired_helpers();",
                "retire_helper(retired);"),
            "one-shot-shutdown": PcmRouteRaceTests.replace_once(source,
                "if (!finish_retired_helpers())", "if (reap_retired_helpers())"),
        }
        prefix = PROGRAM[:PROGRAM.index("int main(int argc, char **argv)")]
        prefix = PcmRouteRaceTests.replace_once(prefix,
            "static pid_t test_waitpid(pid_t process, int *status, int options)",
            "static pid_t lifecycle_waitpid(pid_t process, int *status, int options);\n"
            "static pid_t test_waitpid(pid_t process, int *status, int options)")
        prefix = PcmRouteRaceTests.replace_once(prefix,
            "return __atomic_load_n(&hold_reaping, __ATOMIC_ACQUIRE) ? 0 : waitpid(process, status, options);",
            "return __atomic_load_n(&hold_reaping, __ATOMIC_ACQUIRE) ? 0 : lifecycle_waitpid(process, status, options);")
        marker = '#include "SOURCE_PATH"'
        declarations = ("static int lifecycle_timedwait(pthread_cond_t *, pthread_mutex_t *, const struct timespec *);\n"
                        "static int lifecycle_clock_gettime(clockid_t, struct timespec *);\n"
                        "#define pthread_cond_timedwait lifecycle_timedwait\n"
                        "#define clock_gettime lifecycle_clock_gettime\n")
        prefix = PcmRouteRaceTests.replace_once(prefix, marker, declarations + marker +
            "\n#undef pthread_cond_timedwait\n#undef clock_gettime\n")
        fixture = LIFECYCLE_FIXTURE.read_text(encoding="utf-8")
        for variant, contents in variants.items():
            selected = SOURCE
            if contents is not None:
                selected = cls.evidence / (variant + ".c")
                selected.write_text(contents, encoding="utf-8")
            program = cls.evidence / (variant + "-lifecycle.c")
            program.write_text(prefix.replace("SOURCE_PATH", selected.as_posix()) + fixture, encoding="utf-8")
            for sanitized in (False, True):
                binary = cls.evidence / (variant + ("-asan-ubsan" if sanitized else "-normal"))
                arguments = ["gcc", "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-Wformat=2", "-Wshadow", "-Wconversion",
                             "-Wno-unused-function", "-Wno-unused-variable", "-O1", "-g", "-pthread", "-UNDEBUG",
                             "-DHIBY_PCM_HOST_TEST", "-DFAKE_ALSA", "-I", str(cls.evidence),
                             "-I", str(HEADER.parent), str(program), "-lm", "-o", str(binary)]
                if sanitized:
                    arguments += ["-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer"]
                result = subprocess.run(arguments, capture_output=True, text=True, timeout=90)
                cls.commands.append(dict(arguments=arguments, returncode=result.returncode,
                                         stdout=result.stdout, stderr=result.stderr))
                if result.returncode:
                    raise RuntimeError(result.stderr)
                cls.binaries[variant, sanitized] = binary

    @classmethod
    def input_hashes(cls):
        return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in cls.source_paths}

    @classmethod
    def write_report(cls):
        after = cls.input_hashes()
        passed = (cls.source_hashes == after and bool(cls.cases) and bool(cls.outcomes) and
                  all(case["passed"] for case in cls.cases) and all(run.get("passed") for run in cls.outcomes) and
                  all(command["returncode"] == 0 for command in cls.commands))
        report = dict(scope=getattr(cls, "report_scope", "Actual HiBy PCM C driver; synthetic ALSA, realtime samples and deferred waitpid only"),
                      limitations="No host clock/services changes, real/null audio, Bluetooth, GUI or native product build",
                      source_sha256=cls.source_hashes, source_sha256_after=after,
                      sources_unchanged=cls.source_hashes == after, commands=cls.commands,
                      runs=cls.outcomes, cases=cls.cases, passed=passed)
        (cls.evidence / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("PCM lifecycle evidence:", cls.evidence, flush=True)

    def tearDown(self):
        result = self._outcome.result
        failed = any(getattr(test, "test_case", test).id() == self.id() for test, _ in result.failures + result.errors)
        self.cases.append(dict(test=self.id(), passed=not failed))

    def check_lifecycle(self, scenario, variant="root", expected=0):
        for sanitized in (False, True):
            with self.subTest(scenario=scenario, variant=variant, sanitized=sanitized):
                binary = self.binaries[variant, sanitized]
                log = self.evidence / (binary.name + "-" + scenario + "-" + uuid.uuid4().hex[:8] + ".pcm")
                environment = dict(os.environ, PCM_MODE="good", PCM_LOG=str(log),
                    ASAN_OPTIONS="detect_leaks=1:abort_on_error=1:log_path=" + str(log) + ".asan",
                    UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1:log_path=" + str(log) + ".ubsan")
                outcome = dict(test=self.id(), scenario=scenario, variant=variant, sanitized=sanitized,
                               arguments=[str(binary), scenario], expected_exit=expected, passed=False)
                self.outcomes.append(outcome)
                result = run_isolated_case(outcome["arguments"], environment, timeout=15, record=outcome, cwd=self.evidence)
                self.assertEqual(result.returncode, expected, outcome)
                self.assertEqual(outcome["cleanup_errors"], [])
                self.assertEqual(outcome["session_cleanup"]["survivors"], [])
                self.assertEqual(outcome["stderr"], "")
                self.assertTrue(outcome["stdout"].startswith("TRACE "))
                self.assertEqual(list(self.evidence.glob(log.name + ".asan*")), [])
                self.assertEqual(list(self.evidence.glob(log.name + ".ubsan*")), [])
                outcome["passed"] = True

    def test_shutdown_reaps_kernel_children_before_fixture_cleanup(self):
        self.check_lifecycle("shutdown-natural")

    def test_shutdown_waits_for_deferred_owned_child(self):
        self.check_lifecycle("shutdown-deferred")

    def test_unreapable_child_preserves_ownership_and_bounds_shutdown(self):
        self.check_lifecycle("shutdown-stubborn")

    def test_idle_pump_reaps_without_another_open_or_busy_wait(self):
        self.check_lifecycle("idle-retired")

    def test_realtime_offsets_do_not_spin_idle_or_delay_helper_loss(self):
        self.check_lifecycle("clock-offset-negative")
        self.check_lifecycle("clock-offset-positive")

    def test_restoring_realtime_wait_reproduces_spin_and_stale_route(self):
        self.check_lifecycle("clock-offset-negative", "realtime-wait", 203)
        self.check_lifecycle("clock-offset-positive", "realtime-wait", 203)

    def test_removing_idle_reaper_leaves_owned_zombies(self):
        self.check_lifecycle("idle-retired", "no-idle-reap", 202)

    def test_one_shot_shutdown_misses_deferred_and_stubborn_children(self):
        self.check_lifecycle("shutdown-deferred", "one-shot-shutdown", 201)
        self.check_lifecycle("shutdown-stubborn", "one-shot-shutdown", 204)


@unittest.skipUnless(sys.platform.startswith("linux") and hasattr(os, "P_PIDFD") and hasattr(os, "pidfd_open") and
                     hasattr(signal, "pidfd_send_signal") and shutil.which("gcc"),
                     "requires Linux pidfd/session isolation, a compiler and ALSA development headers")
class PcmOutputStatusTests(unittest.TestCase):
    input_hashes = classmethod(PcmLifecycleTests.input_hashes.__func__)
    write_report = classmethod(PcmLifecycleTests.write_report.__func__)
    tearDown = PcmLifecycleTests.tearDown
    check_status = PcmLifecycleTests.check_lifecycle

    @classmethod
    def setUpClass(cls):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.evidence = project_materials_root(ROOT) / "hiby-pcm-output-status-tests" / (stamp + "-" + uuid.uuid4().hex[:8])
        cls.evidence.mkdir(parents=True, exist_ok=False)
        cls.commands, cls.outcomes, cls.cases = [], [], []
        cls.source_paths = (SOURCE, HEADER, Path(__file__), STATUS_FIXTURE)
        cls.source_hashes = cls.input_hashes()
        cls.binaries = {}
        cls.report_scope = "Actual HiBy PCM output-status getter; coherent lifecycle/route/loss/error snapshots; synthetic ALSA only"
        cls.addClassCleanup(cls.write_report)
        (cls.evidence / "hiby-pcm-test.h").write_text(SHIM, encoding="utf-8")
        source = SOURCE.read_text(encoding="utf-8")
        replace_once = PcmRouteRaceTests.replace_once
        manual_edge = replace_once(source, "else\n                bluetooth_episode_active = false;",
                                   "else if (false)\n                bluetooth_episode_active = false;")
        manual_edge = replace_once(manual_edge, "publish_output_status(0, false, true);",
            "publish_output_status(bluetooth_episode_active && !is_bluetooth(device) ? -ENODEV : 0, "
            "bluetooth_episode_active && !is_bluetooth(device), true);")
        variants = {
            "root": None,
            "clear-sticky": replace_once(source, "if (recovered)\n        error_episode_active = false;",
                "if (recovered) { error_episode_active = false; output_status.loss_generation = 0; output_status.last_error = 0; }"),
            "manual-edge-loss": manual_edge,
            "no-reopen-loss": replace_once(source, "bool lost_bluetooth = !explicit_request && bluetooth_episode_active &&",
                "bool lost_bluetooth = false && !explicit_request && bluetooth_episode_active &&"),
            "refresh-loss-intent": replace_once(source, "output_status.loss_intent_generation = bluetooth_episode_intent;",
                "output_status.loss_intent_generation = route_intent_generation;"),
            "refreshed-fallback": replace_once(source,
                "switch_playback_device(LOCAL_DEVICE, shutdown_requested, NULL, false, recovery_generation)",
                "switch_playback_device(LOCAL_DEVICE, shutdown_requested, NULL, false, route_intent_generation)"),
        }
        prefix = PROGRAM[:PROGRAM.index("int main(int argc, char **argv)")]
        marker = '#include "SOURCE_PATH"'
        declarations = ("static int status_mutex_unlock(pthread_mutex_t *mutex);\n"
                        "static int status_pthread_create(pthread_t *, const pthread_attr_t *, void *(*)(void *), void *);\n"
                        "static int status_condattr_setclock(pthread_condattr_t *, clockid_t);\n"
                        "#define pthread_mutex_unlock status_mutex_unlock\n"
                        "#define pthread_create status_pthread_create\n"
                        "#define pthread_condattr_setclock status_condattr_setclock\n")
        prefix = replace_once(prefix, marker, declarations + marker +
            "\n#undef pthread_mutex_unlock\n#undef pthread_create\n#undef pthread_condattr_setclock\n")
        fixture = STATUS_FIXTURE.read_text(encoding="utf-8")
        for variant, contents in variants.items():
            selected = SOURCE
            if contents is not None:
                selected = cls.evidence / (variant + ".c")
                selected.write_text(contents, encoding="utf-8")
            program = cls.evidence / (variant + "-status.c")
            program.write_text(prefix.replace("SOURCE_PATH", selected.as_posix()) + fixture, encoding="utf-8")
            for sanitized in (False, True):
                binary = cls.evidence / (variant + ("-asan-ubsan" if sanitized else "-normal"))
                arguments = ["gcc", "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-Wformat=2", "-Wshadow", "-Wconversion",
                             "-Wno-unused-function", "-Wno-unused-variable", "-O1", "-g", "-pthread", "-UNDEBUG",
                             "-DHIBY_PCM_HOST_TEST", "-DFAKE_ALSA", "-I", str(cls.evidence),
                             "-I", str(HEADER.parent), str(program), "-lm", "-o", str(binary)]
                if sanitized:
                    arguments += ["-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer"]
                result = subprocess.run(arguments, capture_output=True, text=True, timeout=90)
                cls.commands.append(dict(arguments=arguments, returncode=result.returncode,
                                         stdout=result.stdout, stderr=result.stderr))
                if result.returncode:
                    raise RuntimeError(result.stderr)
                cls.binaries[variant, sanitized] = binary

    def test_getter_before_init_does_not_initialize_pcm(self):
        self.check_status("preinit")

    def test_failed_thread_init_reports_one_error_without_loss(self):
        self.check_status("init-failure")

    def test_failed_sync_init_reports_error_without_framework_or_helpers(self):
        self.check_status("sync-init-failure")

    def test_startup_failure_cancellation_and_manual_wired_are_not_loss(self):
        for scenario in ("startup-failure", "cancelled-candidate", "manual-wired"):
            self.check_status(scenario)

    def test_loss_is_sticky_once_per_committed_bluetooth_episode(self):
        self.check_status("sticky-loss")

    def test_successful_reopen_is_not_loss_but_failed_reopen_is(self):
        self.check_status("reopen-success")
        self.check_status("reopen-failure")

    def test_newer_manual_intent_rejects_old_loss_policy(self):
        self.check_status("newer-manual-intent")

    def test_failed_reopen_with_exhausted_helper_pool_reports_loss(self):
        self.check_status("pool-exhausted-reopen")

    def test_stale_fallback_keeps_new_manual_route_and_original_loss_intent(self):
        self.check_status("stale-fallback")

    def test_failed_wired_retries_do_not_generate_repeated_loss_or_errors(self):
        self.check_status("error-retries")

    def test_concurrent_getters_observe_coherent_route_snapshots(self):
        self.check_status("coherent-snapshots")

    def test_wrapped_generations_are_compared_to_acknowledged_tokens(self):
        self.check_status("generation-wrap")

    def test_causal_mutants_expose_false_missing_and_stale_loss_status(self):
        for scenario, variant, expected in (("sticky-loss", "clear-sticky", 151),
            ("manual-wired", "manual-edge-loss", 152), ("reopen-failure", "no-reopen-loss", 153),
            ("newer-manual-intent", "refresh-loss-intent", 154), ("stale-fallback", "refreshed-fallback", 155)):
            self.check_status(scenario, variant, expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
