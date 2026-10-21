#ifndef USB_STORAGE_HIBY_H
#define USB_STORAGE_HIBY_H

#include <stdbool.h>
#include <stddef.h>

#define HIBY_USB_STORAGE_PATH_SIZE 128
#define HIBY_USB_STORAGE_OPTIONS_SIZE 512

enum hiby_usb_storage_state
{
    HIBY_USB_STORAGE_UNKNOWN,
    HIBY_USB_STORAGE_LOCAL,
    HIBY_USB_STORAGE_PREPARED,
    HIBY_USB_STORAGE_EXPORTED,
    HIBY_USB_STORAGE_RECOVERY
};

enum hiby_usb_storage_error
{
    HIBY_USB_STORAGE_ERROR_NONE,
    HIBY_USB_STORAGE_ERROR_UNVERIFIED,
    HIBY_USB_STORAGE_ERROR_CONFIGURATION,
    HIBY_USB_STORAGE_ERROR_STATE,
    HIBY_USB_STORAGE_ERROR_DETACH,
    HIBY_USB_STORAGE_ERROR_LOCAL,
    HIBY_USB_STORAGE_ERROR_QUIESCE,
    HIBY_USB_STORAGE_ERROR_MOUNT_SNAPSHOT,
    HIBY_USB_STORAGE_ERROR_ALIAS,
    HIBY_USB_STORAGE_ERROR_SYNC,
    HIBY_USB_STORAGE_ERROR_UNMOUNT,
    HIBY_USB_STORAGE_ERROR_REMOUNT_DETECTED,
    HIBY_USB_STORAGE_ERROR_EXPORT,
    HIBY_USB_STORAGE_ERROR_RESTORE,
    HIBY_USB_STORAGE_ERROR_LEASE,
    HIBY_USB_STORAGE_ERROR_REOPEN
};

struct hiby_usb_storage_status
{
    bool success;
    bool safe_to_resume;
    enum hiby_usb_storage_error error;
    int system_error;
    int recovery_error;
    enum hiby_usb_storage_state state;
    bool configuration_verified;
};

struct hiby_usb_storage_mount
{
    char device[HIBY_USB_STORAGE_PATH_SIZE];
    char directory[HIBY_USB_STORAGE_PATH_SIZE];
    char filesystem[32];
    char options[HIBY_USB_STORAGE_OPTIONS_SIZE];
    unsigned long flags;
    unsigned int device_major;
    unsigned int device_minor;
};

struct hiby_usb_storage_operations
{
    int (*detach)(void *context);
    int (*local_ready)(void *context);
    int (*quiesce)(void *context);
    int (*lease_valid)(void *context);
    int (*release)(void *context);
    int (*capture)(void *context, struct hiby_usb_storage_mount *mount);
    int (*overlaps)(void *context, const struct hiby_usb_storage_mount *mount,
                    unsigned int *count);
    int (*synchronize)(void *context);
    int (*close_local)(void *context);
    int (*unmount)(void *context, const struct hiby_usb_storage_mount *mount);
    int (*mount)(void *context, const struct hiby_usb_storage_mount *mount);
    int (*reopen_local)(void *context);
    int (*attach)(void *context, const struct hiby_usb_storage_mount *mount);
};

struct hiby_usb_storage
{
    struct hiby_usb_storage_status status;
    const struct hiby_usb_storage_operations *operations;
    void *context;
    struct hiby_usb_storage_mount saved_mount;
    bool saved;
    bool lease;
    bool closed;
};

struct hiby_usb_storage_io
{
    int (*open)(void *context, const char *path, bool write);
    int (*read)(void *context, int descriptor, char *buffer, size_t size);
    int (*write)(void *context, int descriptor, const char *buffer, size_t size);
    int (*close)(void *context, int descriptor);
};

void hiby_usb_storage_init(struct hiby_usb_storage *storage,
                           const struct hiby_usb_storage_operations *operations,
                           void *context, bool configuration_verified);
struct hiby_usb_storage_status hiby_usb_storage_prepare(struct hiby_usb_storage *storage);
struct hiby_usb_storage_status hiby_usb_storage_export(struct hiby_usb_storage *storage);
struct hiby_usb_storage_status hiby_usb_storage_restore(struct hiby_usb_storage *storage);
int hiby_usb_storage_checked_value(const struct hiby_usb_storage_io *operations,
                                   void *context, const char *path,
                                   const char *value, const char *expected);

struct hiby_usb_storage_status hiby_usb_storage_target_prepare(void);
struct hiby_usb_storage_status hiby_usb_storage_target_export(void);
struct hiby_usb_storage_status hiby_usb_storage_target_restore(void);
struct hiby_usb_storage_status hiby_usb_storage_target_status(void);
bool hiby_usb_storage_target_safe_to_resume(void);

#endif
