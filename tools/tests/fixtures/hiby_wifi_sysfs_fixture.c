#define __wrap_open legacy_open
#define __wrap___open_2 legacy_open_2
#define __wrap_fstat legacy_fstat
#define __wrap___fxstat legacy_fxstat
#define __wrap_read legacy_read
#define __wrap___read_chk legacy_read_chk
#define __wrap_write legacy_write
#define __wrap_opendir legacy_opendir
#define __wrap_readdir legacy_readdir
#define __wrap_closedir legacy_closedir
#define __wrap_dirfd legacy_dirfd
#define __wrap_openat legacy_openat
#define __wrap___openat_2 legacy_openat_2
#define main legacy_power_main
#include "hiby_power_control_fixture.c"
#undef main
#undef __wrap_open
#undef __wrap___open_2
#undef __wrap_fstat
#undef __wrap___fxstat
#undef __wrap_read
#undef __wrap___read_chk
#undef __wrap_write
#undef __wrap_opendir
#undef __wrap_readdir
#undef __wrap_closedir
#undef __wrap_dirfd
#undef __wrap_openat
#undef __wrap___openat_2

static bool directory_active;
static unsigned int directory_position;
static unsigned int directory_reads;
static unsigned int attribute_position[8];
static unsigned int attribute_radio[8];
static const char *attribute_name[8];
static bool soft_blocks[66];
static unsigned int soft_writes;
static struct dirent directory_entry;

DIR *__wrap_opendir(const char *path)
{
    CHECK(!strcmp(path, "/sys/class/rfkill") && !directory_active);
    if (is_case("missing"))
    {
        errno = ENOENT;
        return NULL;
    }
    if (is_case("directory-denied") || is_case("directory-storm"))
    {
        errno = is_case("directory-storm") ? EINTR : EACCES;
        return NULL;
    }
    directory_active = true;
    directory_position = 0;
    ++opens;
    return (DIR *)&directory_active;
}

struct dirent *__wrap_readdir(DIR *directory)
{
    CHECK(directory == (DIR *)&directory_active && directory_active);
    ++directory_reads;
    if (is_case("directory-read-error") || is_case("directory-read-storm"))
    {
        errno = is_case("directory-read-storm") ? EINTR : EIO;
        return NULL;
    }
    if (is_case("none"))
        return NULL;
    unsigned int total = is_case("too-many") ? 66 : 3;
    if (directory_position == total)
        return NULL;
    if (is_case("junk") && directory_position == 0)
        strcpy(directory_entry.d_name, "rfkill0/../bluetooth");
    else
        snprintf(directory_entry.d_name, sizeof(directory_entry.d_name),
                 "rfkill%u", directory_position);
    ++directory_position;
    return &directory_entry;
}

int __wrap_closedir(DIR *directory)
{
    CHECK(directory == (DIR *)&directory_active && directory_active);
    directory_active = false;
    ++closes;
    return is_case("directory-close-error") ? failure(EIO) : 0;
}

int __wrap_open(const char *path, int flags, ...)
{
    CHECK((flags & (O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW)) ==
          (O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW));
    CHECK(!strcmp(path, "/dev/rfkill"));
    return failure(ENOENT);
}

int __wrap___open_2(const char *path, int flags)
{
    return __wrap_open(path, flags);
}

int __wrap_dirfd(DIR *directory)
{
    CHECK(directory == (DIR *)&directory_active && directory_active);
    return 100;
}

int __wrap_openat(int directory, const char *path, int flags, ...)
{
    CHECK(directory_active);
    if (directory == 100)
    {
        CHECK(flags == (O_RDONLY | O_DIRECTORY | O_CLOEXEC));
        unsigned int radio;
        int consumed = 0;
        CHECK(sscanf(path, "rfkill%u%n", &radio, &consumed) == 1);
        CHECK(consumed > 0 && !path[consumed] && radio < 66);
        int descriptor = allocate(RADIO_DIRECTORY);
        attribute_radio[descriptor] = radio;
        return descriptor;
    }
    descriptor_is(directory, RADIO_DIRECTORY);
    CHECK((flags & (O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW)) ==
          (O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW));
    unsigned int radio = attribute_radio[directory];
    const char *attribute = path;
    CHECK(!strcmp(attribute, "type") || !strcmp(attribute, "soft") || !strcmp(attribute, "hard"));
    bool changing = (flags & O_ACCMODE) == O_WRONLY;
    CHECK(!changing || (!query_only && !strcmp(attribute, "soft") && radio != 1));
    if (is_case("attribute-missing"))
        return failure(ENOENT);
    if (is_case("attribute-symlink"))
        return failure(ELOOP);
    if (is_case("write-denied") && changing)
        return failure(EACCES);
    int descriptor = allocate(changing ? RADIO_WRITE : RADIO_READ);
    attribute_position[descriptor] = 0;
    attribute_radio[descriptor] = radio;
    attribute_name[descriptor] = !strcmp(attribute, "type") ? "type" :
        !strcmp(attribute, "soft") ? "soft" : "hard";
    return descriptor;
}

int __wrap___openat_2(int directory, const char *path, int flags)
{
    return __wrap_openat(directory, path, flags);
}

int __wrap_fstat(int descriptor, struct stat *status)
{
    CHECK(descriptor >= 0 && descriptor < 8 && descriptors[descriptor] != CLOSED);
    memset(status, 0, sizeof(*status));
    status->st_mode = S_IFREG;
    return 0;
}

int __wrap___fxstat(int version, int descriptor, struct stat *status)
{
    (void)version;
    return __wrap_fstat(descriptor, status);
}

ssize_t __wrap_read(int descriptor, void *buffer, size_t capacity)
{
    descriptor_is(descriptor, RADIO_READ);
    ++reads;
    if (is_case("read-storm") || (is_case("read-eintr") && reads == 1))
        return failure(EINTR);
    unsigned int radio = attribute_radio[descriptor];
    const char *attribute = attribute_name[descriptor];
    const char *data;
    if (!strcmp(attribute, "type"))
        data = radio == 1 || is_case("bt-only") ? "bluetooth\n" : "wlan\n";
    else if (!strcmp(attribute, "soft"))
        data = soft_blocks[radio] ? "1\n" : "0\n";
    else
        data = is_case("hard-blocked") ? "1\n" : "0\n";
    if ((!strcmp(attribute, "soft") && is_case("bad-soft")) ||
        (!strcmp(attribute, "hard") && is_case("bad-hard")))
        data = "2\n";
    if (!strcmp(attribute, "type") && is_case("bad-type"))
        data = "\n";
    if (is_case("overlong"))
        data = "wlanxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n";
    size_t length = strlen(data);
    size_t position = attribute_position[descriptor];
    size_t count = length - position;
    if (count > capacity)
        count = capacity;
    if (is_case("read-short") && count > 1)
        count = 1;
    memcpy(buffer, data + position, count);
    attribute_position[descriptor] += count;
    return count;
}

ssize_t __wrap___read_chk(int descriptor, void *buffer, size_t capacity, size_t size)
{
    CHECK(capacity <= size);
    return __wrap_read(descriptor, buffer, capacity);
}

ssize_t __wrap_write(int descriptor, const void *buffer, size_t size)
{
    descriptor_is(descriptor, RADIO_WRITE);
    ++writes;
    unsigned int radio = attribute_radio[descriptor];
    CHECK(!query_only && !strcmp(attribute_name[descriptor], "soft") && radio != 1);
    CHECK(size == 2 && !memcmp(buffer, requested_enabled ? "0\n" : "1\n", 2));
    if (is_case("write-storm") || (is_case("write-eintr") && writes == 1))
        return failure(EINTR);
    if (is_case("short-write"))
        return 1;
    if (!is_case("stale"))
        soft_blocks[radio] = !requested_enabled;
    ++soft_writes;
    return 2;
}

int main(int count, char **arguments)
{
    CHECK(count == 3);
    scenario = arguments[2];
    query_only = !strcmp(arguments[1], "query");
    requested_enabled = !strcmp(arguments[1], "enable");
    CHECK(query_only || requested_enabled || !strcmp(arguments[1], "disable"));
    extended_wifi = true;
    interface_flags[0] = IFF_BROADCAST | IFF_MULTICAST |
        (query_only || !requested_enabled ? IFF_UP : 0);
    soft_blocks[1] = true;
    if (requested_enabled)
        soft_blocks[0] = soft_blocks[2] = true;
    struct hiby_wifi_result result = query_only ? hiby_wifi_get_state() :
        hiby_wifi_set_enabled(requested_enabled);
    no_descriptors();
    CHECK(!directory_active && soft_blocks[1]);
    CHECK(!spawn_calls && !kill_calls && !sync_calls && !reboot_calls);
    CHECK(directory_reads <= 2 * HIBY_SYSFS_TEST_ENTRY_BOUND);
    CHECK((interface_flags[0] & ~IFF_UP) == (IFF_BROADCAST | IFF_MULTICAST));
    CHECK(result.interfaces_present == 1 && result.interface_read_error == 0);
    bool no_api = is_case("missing");
    bool no_wlan = is_case("none") || is_case("bt-only");
    bool bad_read = is_case("bad-soft") || is_case("bad-hard") || is_case("bad-type") ||
        is_case("overlong") || is_case("read-storm") || is_case("directory-denied") ||
        is_case("directory-storm") || is_case("directory-read-error") ||
        is_case("directory-read-storm") || is_case("directory-close-error") ||
        is_case("too-many") || is_case("attribute-symlink");
    bool missing_attribute = is_case("attribute-missing");
    bool bad_write = is_case("write-denied") || is_case("write-storm") || is_case("short-write");
    if (bad_read)
        CHECK(result.state == HIBY_WIFI_ERROR && result.rfkill_read_error != 0);
    else if (bad_write && !query_only)
        CHECK(result.rfkill_error != 0 && result.state != HIBY_WIFI_ENABLED);
    else if (no_api || no_wlan || missing_attribute)
    {
        CHECK(result.state == (query_only || requested_enabled ?
            no_wlan ? HIBY_WIFI_NO_RADIO : HIBY_WIFI_UNCONFIRMED : HIBY_WIFI_INTERFACE_DOWN));
        CHECK(result.state != HIBY_WIFI_BLOCKED);
    }
    else if (is_case("hard-blocked"))
        CHECK(result.state == HIBY_WIFI_HARD_BLOCKED);
    else if (is_case("stale") && !query_only)
        CHECK(result.state != (requested_enabled ? HIBY_WIFI_ENABLED : HIBY_WIFI_BLOCKED));
    else
        CHECK(result.state == (query_only || requested_enabled ? HIBY_WIFI_ENABLED : HIBY_WIFI_BLOCKED));
    if (!no_api && !missing_attribute && !bad_read)
        CHECK(result.rfkill_sysfs);
    if (query_only)
        CHECK(!writes && !soft_writes && result.interfaces_up == 1);
    if (!bad_read && !bad_write && !no_api && !no_wlan && !missing_attribute && !query_only)
        CHECK(soft_writes == (is_case("junk") ? 1u : 2u));
    printf("PASS sysfs %s %s state=%d radios=%u down=%u writes=%u\n",
           arguments[1], scenario, result.state, result.wlan_radios, result.interfaces_down, writes);
    return 0;
}
