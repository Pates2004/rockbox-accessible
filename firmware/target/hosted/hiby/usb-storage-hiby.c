#include "usb-storage-hiby.h"

#include <errno.h>
#include <string.h>

static struct hiby_usb_storage_status fail(struct hiby_usb_storage *storage,
                                          enum hiby_usb_storage_error error,
                                          int system_error)
{
    storage->status.success = false;
    storage->status.error = error;
    storage->status.system_error = system_error;
    storage->status.recovery_error = 0;
    return storage->status;
}

static bool complete_operations(const struct hiby_usb_storage_operations *operations)
{
    return operations && operations->detach && operations->local_ready &&
        operations->quiesce && operations->lease_valid && operations->release &&
        operations->capture && operations->overlaps && operations->synchronize &&
        operations->close_local && operations->unmount && operations->mount &&
        operations->reopen_local && operations->attach;
}

void hiby_usb_storage_init(struct hiby_usb_storage *storage,
                           const struct hiby_usb_storage_operations *operations,
                           void *context, bool configuration_verified)
{
    memset(storage, 0, sizeof(*storage));
    storage->operations = operations;
    storage->context = context;
    storage->status.configuration_verified = configuration_verified;
    storage->status.state = HIBY_USB_STORAGE_UNKNOWN;
    storage->status.error = HIBY_USB_STORAGE_ERROR_UNVERIFIED;
}

static bool valid_mount(const struct hiby_usb_storage_mount *mount)
{
    return memchr(mount->device, 0, sizeof(mount->device)) &&
        memchr(mount->directory, 0, sizeof(mount->directory)) &&
        memchr(mount->filesystem, 0, sizeof(mount->filesystem)) &&
        memchr(mount->options, 0, sizeof(mount->options)) &&
        mount->device[0] == '/' && mount->directory[0] == '/' &&
        mount->filesystem[0] != 0 && mount->device_major != 0;
}

static bool same_mount(const struct hiby_usb_storage_mount *first,
                        const struct hiby_usb_storage_mount *second)
{
    return valid_mount(second) &&
        first->device_major == second->device_major &&
        first->device_minor == second->device_minor &&
        first->flags == second->flags &&
        strcmp(first->device, second->device) == 0 &&
        strcmp(first->directory, second->directory) == 0 &&
        strcmp(first->filesystem, second->filesystem) == 0 &&
        strcmp(first->options, second->options) == 0;
}

static struct hiby_usb_storage_status recovery_failure(struct hiby_usb_storage *storage,
                                                       enum hiby_usb_storage_error error,
                                                       int system_error)
{
    storage->status.state = HIBY_USB_STORAGE_RECOVERY;
    storage->status.safe_to_resume = false;
    return fail(storage, error, system_error);
}

struct hiby_usb_storage_status hiby_usb_storage_restore(struct hiby_usb_storage *storage)
{
    const struct hiby_usb_storage_operations *operations = storage->operations;
    struct hiby_usb_storage_mount current;
    unsigned int count;
    int result;

    if (!operations || !operations->detach || !operations->local_ready)
        return recovery_failure(storage, HIBY_USB_STORAGE_ERROR_CONFIGURATION, EINVAL);
    result = operations->detach(storage->context);
    if (result)
        return recovery_failure(storage, HIBY_USB_STORAGE_ERROR_DETACH, result);

    if (storage->saved)
    {
        if (!complete_operations(operations))
            return recovery_failure(storage, HIBY_USB_STORAGE_ERROR_CONFIGURATION, EINVAL);
        result = operations->overlaps(storage->context, &storage->saved_mount, &count);
        if (result)
            return recovery_failure(storage, HIBY_USB_STORAGE_ERROR_MOUNT_SNAPSHOT, result);
        if (count == 0)
        {
            if (!storage->lease || (result = operations->lease_valid(storage->context)))
                return recovery_failure(storage, HIBY_USB_STORAGE_ERROR_LEASE,
                                        storage->lease ? result : EPERM);
            result = operations->mount(storage->context, &storage->saved_mount);
            if (result)
                return recovery_failure(storage, HIBY_USB_STORAGE_ERROR_RESTORE, result);
        }

        memset(&current, 0, sizeof(current));
        result = operations->capture(storage->context, &current);
        if (result || !same_mount(&storage->saved_mount, &current))
            return recovery_failure(storage, HIBY_USB_STORAGE_ERROR_RESTORE,
                                    result ? result : EINVAL);
        result = operations->overlaps(storage->context, &storage->saved_mount, &count);
        if (result || count == 0)
            return recovery_failure(storage, HIBY_USB_STORAGE_ERROR_ALIAS,
                                    result ? result : EBUSY);
    }

    result = operations->local_ready(storage->context);
    if (result)
        return recovery_failure(storage, HIBY_USB_STORAGE_ERROR_LOCAL, result);
    if (storage->closed)
    {
        result = operations->reopen_local(storage->context);
        if (result)
            return recovery_failure(storage, HIBY_USB_STORAGE_ERROR_REOPEN, result);
        storage->closed = false;
    }
    if (storage->lease)
    {
        result = operations->release(storage->context);
        if (result)
            return recovery_failure(storage, HIBY_USB_STORAGE_ERROR_LEASE, result);
        storage->lease = false;
    }
    storage->saved = false;
    storage->status.state = HIBY_USB_STORAGE_LOCAL;
    storage->status.safe_to_resume = true;
    storage->status.success = true;
    storage->status.error = HIBY_USB_STORAGE_ERROR_NONE;
    storage->status.system_error = 0;
    storage->status.recovery_error = 0;
    return storage->status;
}

static struct hiby_usb_storage_status rollback(struct hiby_usb_storage *storage,
                                               enum hiby_usb_storage_error error,
                                               int system_error)
{
    struct hiby_usb_storage_status restored = hiby_usb_storage_restore(storage);
    struct hiby_usb_storage_status status = fail(storage, error, system_error);
    status.recovery_error = restored.success ? 0 : restored.system_error;
    storage->status = status;
    return status;
}

struct hiby_usb_storage_status hiby_usb_storage_prepare(struct hiby_usb_storage *storage)
{
    const struct hiby_usb_storage_operations *operations = storage->operations;
    unsigned int count;
    int result;

    if (storage->status.state == HIBY_USB_STORAGE_PREPARED ||
        storage->status.state == HIBY_USB_STORAGE_EXPORTED || storage->saved || storage->lease)
        return fail(storage, HIBY_USB_STORAGE_ERROR_STATE, EBUSY);
    if (!hiby_usb_storage_restore(storage).success)
        return storage->status;
    if (!storage->status.configuration_verified)
        return fail(storage, HIBY_USB_STORAGE_ERROR_UNVERIFIED, ENOTSUP);
    if (!complete_operations(operations))
        return fail(storage, HIBY_USB_STORAGE_ERROR_CONFIGURATION, EINVAL);

    result = operations->quiesce(storage->context);
    if (result)
        return fail(storage, HIBY_USB_STORAGE_ERROR_QUIESCE, result);
    storage->lease = true;
    result = operations->lease_valid(storage->context);
    if (result)
        return rollback(storage, HIBY_USB_STORAGE_ERROR_LEASE, result);
    memset(&storage->saved_mount, 0, sizeof(storage->saved_mount));
    result = operations->capture(storage->context, &storage->saved_mount);
    if (result || !valid_mount(&storage->saved_mount))
        return rollback(storage, HIBY_USB_STORAGE_ERROR_MOUNT_SNAPSHOT,
                        result ? result : EINVAL);
    storage->saved = true;
    result = operations->overlaps(storage->context, &storage->saved_mount, &count);
    if (result || count != 1)
        return rollback(storage, HIBY_USB_STORAGE_ERROR_ALIAS, result ? result : EBUSY);
    result = operations->synchronize(storage->context);
    if (result)
        return rollback(storage, HIBY_USB_STORAGE_ERROR_SYNC, result);
    storage->closed = true;
    result = operations->close_local(storage->context);
    if (result)
        return rollback(storage, HIBY_USB_STORAGE_ERROR_LOCAL, result);
    result = operations->lease_valid(storage->context);
    if (result)
        return rollback(storage, HIBY_USB_STORAGE_ERROR_LEASE, result);
    storage->status.safe_to_resume = false;
    result = operations->unmount(storage->context, &storage->saved_mount);
    if (result)
        return rollback(storage, HIBY_USB_STORAGE_ERROR_UNMOUNT, result);
    result = operations->overlaps(storage->context, &storage->saved_mount, &count);
    if (result || count != 0)
        return rollback(storage, HIBY_USB_STORAGE_ERROR_REMOUNT_DETECTED,
                        result ? result : EBUSY);
    result = operations->lease_valid(storage->context);
    if (result)
        return rollback(storage, HIBY_USB_STORAGE_ERROR_LEASE, result);
    storage->status.state = HIBY_USB_STORAGE_PREPARED;
    storage->status.success = true;
    return storage->status;
}

struct hiby_usb_storage_status hiby_usb_storage_export(struct hiby_usb_storage *storage)
{
    const struct hiby_usb_storage_operations *operations = storage->operations;
    unsigned int count;
    int result;

    if (!storage->status.configuration_verified)
        return fail(storage, HIBY_USB_STORAGE_ERROR_UNVERIFIED, ENOTSUP);
    if (storage->status.state != HIBY_USB_STORAGE_PREPARED || !storage->saved ||
        !storage->lease || !complete_operations(operations))
        return fail(storage, HIBY_USB_STORAGE_ERROR_STATE, EINVAL);
    result = operations->lease_valid(storage->context);
    if (result)
        return rollback(storage, HIBY_USB_STORAGE_ERROR_LEASE, result);
    result = operations->overlaps(storage->context, &storage->saved_mount, &count);
    if (result || count != 0)
        return rollback(storage, HIBY_USB_STORAGE_ERROR_REMOUNT_DETECTED,
                        result ? result : EBUSY);
    result = operations->attach(storage->context, &storage->saved_mount);
    if (result)
        return rollback(storage, HIBY_USB_STORAGE_ERROR_EXPORT, result);
    result = operations->lease_valid(storage->context);
    if (result)
        return rollback(storage, HIBY_USB_STORAGE_ERROR_LEASE, result);
    result = operations->overlaps(storage->context, &storage->saved_mount, &count);
    if (result || count != 0)
        return rollback(storage, HIBY_USB_STORAGE_ERROR_REMOUNT_DETECTED,
                        result ? result : EBUSY);
    storage->status.state = HIBY_USB_STORAGE_EXPORTED;
    storage->status.success = true;
    storage->status.safe_to_resume = false;
    storage->status.error = HIBY_USB_STORAGE_ERROR_NONE;
    storage->status.system_error = 0;
    storage->status.recovery_error = 0;
    return storage->status;
}

int hiby_usb_storage_checked_value(const struct hiby_usb_storage_io *operations,
                                   void *context, const char *path,
                                   const char *value, const char *expected)
{
    char buffer[HIBY_USB_STORAGE_PATH_SIZE];
    size_t length;
    size_t received = 0;
    int descriptor, result, closed;

    if (!operations || !operations->open || !operations->read ||
        !operations->write || !operations->close || !path || !value || !expected)
        return EINVAL;
    length = strlen(value);
    if (length == 0 || length >= sizeof(buffer) || strlen(expected) >= sizeof(buffer))
        return EINVAL;
    descriptor = operations->open(context, path, true);
    if (descriptor < 0)
        return -descriptor;
    result = operations->write(context, descriptor, value, length);
    closed = operations->close(context, descriptor);
    if (result < 0)
        return -result;
    if ((size_t)result != length || closed)
        return closed ? closed : EIO;
    descriptor = operations->open(context, path, false);
    if (descriptor < 0)
        return -descriptor;
    do
    {
        result = operations->read(context, descriptor, buffer + received,
                                  sizeof(buffer) - 1 - received);
        if (result <= 0)
            break;
        if ((size_t)result > sizeof(buffer) - 1 - received)
        {
            result = -EOVERFLOW;
            break;
        }
        received += (size_t)result;
    }
    while (received < sizeof(buffer) - 1);
    closed = operations->close(context, descriptor);
    if (result < 0)
        return -result;
    if (closed)
        return closed;
    if (received >= sizeof(buffer) - 1)
        return EOVERFLOW;
    buffer[received] = 0;
    if (received > 0 && buffer[received - 1] == '\n')
        buffer[--received] = 0;
    if (memchr(buffer, 0, received) || strcmp(buffer, expected) != 0)
        return EIO;
    return 0;
}
