#ifndef RB_ESPEAK_SHADOW_WCTYPE_H
#define RB_ESPEAK_SHADOW_WCTYPE_H
#include "native_only.h"
#include_next <wctype.h>
#include "../native_runtime.h"
#undef iswalnum
#undef iswalpha
#undef iswdigit
#undef iswlower
#undef iswpunct
#undef iswspace
#undef iswupper
#undef towlower
#undef towupper
#define iswalnum rb_espeak_iswalnum
#define iswalpha rb_espeak_iswalpha
#define iswdigit rb_espeak_iswdigit
#define iswlower rb_espeak_iswlower
#define iswpunct rb_espeak_iswpunct
#define iswspace rb_espeak_iswspace
#define iswupper rb_espeak_iswupper
#define towlower rb_espeak_towlower
#define towupper rb_espeak_towupper
#endif
