#ifndef RB_ESPEAK_SHADOW_ERRNO_H
#define RB_ESPEAK_SHADOW_ERRNO_H
#include "native_only.h"
#include_next <errno.h>
#include "../native_runtime.h"
#undef errno
#define errno rb_espeak_errno
#endif
