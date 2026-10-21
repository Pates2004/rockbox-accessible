#ifndef RB_ESPEAK_SHADOW_STRING_H
#define RB_ESPEAK_SHADOW_STRING_H
#include "native_only.h"
#include_next <string.h>
#include "../native_runtime.h"
#define strspn rb_espeak_strspn
#define strtok rb_espeak_strtok
#endif
