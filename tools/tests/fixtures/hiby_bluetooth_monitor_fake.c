#define _GNU_SOURCE 1
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <time.h>
#include <unistd.h>

static void pause_forever(void)
{
    for (;;)
        pause();
}

static void record_number(const char *name, long value)
{
    char path[4096];
    if (snprintf(path, sizeof(path), "%s/%s", TEST_DIRECTORY, name) >=
        (int)sizeof(path))
        _exit(81);
    FILE *output = fopen(path, "w");
    if (!output || fprintf(output, "%ld\n", value) < 0 || fclose(output))
        _exit(82);
}

static bool write_all(int descriptor, const char *bytes, size_t length)
{
    size_t written = 0;
    while (written < length)
    {
        ssize_t count = write(descriptor, bytes + written, length - written);
        if (count > 0)
            written += (size_t)count;
        else if (count < 0 && errno == EINTR)
            continue;
        else
            return false;
    }
    return true;
}

int main(int count, char **arguments)
{
    pid_t parent = getppid();
    int death_signal = 0;
    if (parent == 1 || prctl(PR_GET_PDEATHSIG, &death_signal) ||
        death_signal != SIGTERM || getppid() != parent)
        return 70;
    if (count != 11 || strcmp(arguments[0], TEST_EXECUTABLE) ||
        strcmp(arguments[1], "--system") || strcmp(arguments[2], "--profile"))
        return 71;
    for (int position = 3; position < count; position++)
        if (!strstr(arguments[position], "type='signal'") ||
            strstr(arguments[position], "StartDiscovery") ||
            strstr(arguments[position], "org.bluealsa.PCM1"))
            return 72;
    DIR *descriptors = opendir("/proc/self/fd");
    if (!descriptors)
        return 73;
    int inherited = 0;
    struct dirent *entry;
    while ((entry = readdir(descriptors)))
    {
        char *end = NULL;
        long descriptor = strtol(entry->d_name, &end, 10);
        if (end != entry->d_name && !*end && descriptor > 2 &&
            descriptor != dirfd(descriptors))
            inherited++;
    }
    closedir(descriptors);
    record_number("inherited", inherited);
    record_number("pid", getpid());
    char mode[64] = "echo";
    FILE *configuration = fopen(TEST_DIRECTORY "/mode", "r");
    if (!configuration || !fgets(mode, sizeof(mode), configuration) ||
        fclose(configuration))
        return 74;
    mode[strcspn(mode, "\n")] = '\0';
    if (!strcmp(mode, "ignoreterm"))
    {
        if (prctl(PR_SET_PDEATHSIG, SIGKILL))
            return 80;
        signal(SIGTERM, SIG_IGN);
    }
    if (!strcmp(mode, "descendant"))
    {
        pid_t descendant = fork();
        if (!descendant)
        {
            if (prctl(PR_SET_PDEATHSIG, SIGKILL) || getppid() != getpgrp())
                _exit(80);
            pause_forever();
        }
        if (descendant < 0)
            return 75;
        record_number("descendant", descendant);
    }
    if (!strcmp(mode, "stderr"))
        fputs("sig\t1700000000.123456\t1\t:1.2\t<none>\t/\torg.freedesktop.DBus.ObjectManager\tInterfacesRemoved\n", stderr);
    if (!strcmp(mode, "closeoutput"))
        close(STDOUT_FILENO);
    record_number("ready", 1);
    if (!strcmp(mode, "exit"))
        return 0;
    if (!strcmp(mode, "closeoutput") || !strcmp(mode, "ignoreterm") ||
        !strcmp(mode, "descendant") || !strcmp(mode, "stderr"))
        pause_forever();
    if (!strcmp(mode, "flood") || !strcmp(mode, "eventflood"))
    {
        char noise[1024];
        memset(noise, 'x', sizeof(noise));
        const char event[] = "sig\t1700000000.123456\t1\t:1.2\t<none>\t/\torg.freedesktop.DBus.ObjectManager\tInterfacesAdded\n";
        const char *bytes = !strcmp(mode, "eventflood") ? event : noise;
        size_t length = !strcmp(mode, "eventflood") ? sizeof(event) - 1 : sizeof(noise);
        for (;;)
            if (!write_all(STDOUT_FILENO, bytes, length))
                return 76;
    }
    int input = open(TEST_DIRECTORY "/input", O_RDONLY | O_CLOEXEC);
    if (input < 0)
        return 77;
    char bytes[4096];
    for (;;)
    {
        ssize_t received = read(input, bytes, sizeof(bytes));
        if (received > 0)
        {
            if (!write_all(STDOUT_FILENO, bytes, (size_t)received))
                return 78;
        }
        else if (received < 0 && errno != EINTR)
            return 79;
        else if (!received)
        {
            struct timespec duration = { 0, 5000000 };
            nanosleep(&duration, NULL);
        }
    }
}
