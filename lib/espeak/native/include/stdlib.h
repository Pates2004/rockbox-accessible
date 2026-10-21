#ifndef RB_ESPEAK_SHADOW_STDLIB_H
#define RB_ESPEAK_SHADOW_STDLIB_H
#include "native_only.h"
#include_next <stdlib.h>
#include "../native_runtime.h"
#define malloc rb_espeak_malloc
#define calloc rb_espeak_calloc
#define realloc rb_espeak_realloc
#define free rb_espeak_free
#define getenv rb_espeak_getenv
#define atof rb_espeak_atof
#define strtod rb_espeak_strtod
#define strtol rb_espeak_strtol
#define strtoul rb_espeak_strtoul
#define mbtowc rb_espeak_mbtowc
#define wctomb rb_espeak_wctomb
#define mbstowcs rb_espeak_mbstowcs
#define wcstombs rb_espeak_wcstombs
#undef abs
#define abs rb_espeak_abs
#endif
