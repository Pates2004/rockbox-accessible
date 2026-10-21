#define _GNU_SOURCE 1
#include "../../../firmware/target/hosted/hiby/power-control-hiby.c"
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
#ifdef HIBY_VENDOR_DESCRIPTORS_TEST
#include <gnu/libc-version.h>
static char **vendor_arguments;
#endif

extern int __real_posix_spawn(pid_t *process, const char *path,
    const posix_spawn_file_actions_t *actions, const posix_spawnattr_t *attributes,
    char *const arguments[], char *const environment[]);

int __wrap_posix_spawn(pid_t *process, const char *path,
    const posix_spawn_file_actions_t *actions, const posix_spawnattr_t *attributes,
    char *const arguments[], char *const environment[])
{
    assert(!strcmp(path, "/bin/busybox"));
    assert(!strcmp(arguments[0], path) && !strcmp(arguments[1], "dd"));
    assert(!strcmp(arguments[2], "of=/proc/self/fd/9"));
    assert(!strcmp(arguments[3], "bs=64") && !strcmp(arguments[4], "count=1") && !arguments[5]);
#ifdef HIBY_VENDOR_DESCRIPTORS_TEST
    char *controlled_arguments[] = { "/usr/bin/python3", "-I", vendor_arguments[3],
        vendor_arguments[1], vendor_arguments[4], vendor_arguments[5], vendor_arguments[6],
        vendor_arguments[7], vendor_arguments[8], NULL };
    return __real_posix_spawn(process, "/usr/bin/python3", actions, attributes,
        controlled_arguments, environment);
#else
    char *controlled_arguments[] = { "/bin/dd", arguments[2], arguments[3], arguments[4], NULL };
    return __real_posix_spawn(process, "/bin/dd", actions, attributes,
        controlled_arguments, environment);
#endif
}

int main(int count, char **arguments)
{
#ifdef HIBY_VENDOR_DESCRIPTORS_TEST
    assert(count == 9);
    vendor_arguments = arguments;
    assert(!strcmp(gnu_get_libc_version(), "2.22"));
    printf("Actual parent libc: %s\n", gnu_get_libc_version());
#else
    assert(count == 3);
#endif
    assert(!strncmp(arguments[1], "controlled-", 11));
    assert(!strchr(arguments[1], '/') && !strchr(arguments[1], '\\'));
    int topology = atoi(arguments[2]);
    assert(topology >= 0 && topology <= 3);
    int target = open(arguments[1], O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
    assert(target == 3);
    struct stat status;
    assert(!fstat(target, &status) && S_ISREG(status.st_mode));
    int fillers[5] = { -1, -1, -1, -1, -1 };
    if (topology == 1)
    {
        int moved = fcntl(target, F_DUPFD_CLOEXEC, 9);
        assert(moved == 9 && !close(target));
        target = moved;
    }
    if (topology >= 2)
    {
        unsigned int filled = topology == 2 ? 5 : 4;
        for (unsigned int position = 0; position < filled; ++position)
        {
            fillers[position] = open("/dev/null", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
            assert(fillers[position] == (int)position + 4);
        }
    }
    int control_result = wifi_control_write(target, "mmc0:0001:2\n", sizeof("mmc0:0001:2\n") - 1, 0);
    if (control_result)
        fprintf(stderr, "CONTROL_RESULT=%d topology=%d\n", control_result, topology);
    assert(!control_result);
    assert(hiby_wifi_settled() && !close(target));
    for (unsigned int position = 0; position < 5; ++position)
        if (fillers[position] >= 0)
            assert(!close(fillers[position]));
    return 0;
}
