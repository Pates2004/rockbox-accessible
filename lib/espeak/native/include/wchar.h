#ifndef RB_ESPEAK_SHADOW_WCHAR_H
#define RB_ESPEAK_SHADOW_WCHAR_H
#include "native_only.h"
#include "../native_runtime.h"
#include <wctype.h>
#define mbstate_t rb_espeak_mbstate_t
#define wcslen rb_espeak_wcslen
#define wcschr rb_espeak_wcschr
#define wcsncpy rb_espeak_wcsncpy
#define wcsncmp rb_espeak_wcsncmp
#define wcstod rb_espeak_wcstod
#define mbrtowc rb_espeak_mbrtowc
#define wcrtomb rb_espeak_wcrtomb
#define mbsinit rb_espeak_mbsinit
#endif
