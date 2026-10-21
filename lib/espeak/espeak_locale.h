#ifndef RB_ESPEAK_LOCALE_H
#define RB_ESPEAK_LOCALE_H

#ifdef _WIN32
#include <locale.h>
#include <wctype.h>

extern thread_local _locale_t espeak_text_locale;

#define iswalnum(character) _iswalnum_l((character), espeak_text_locale)
#define iswalpha(character) _iswalpha_l((character), espeak_text_locale)
#define iswdigit(character) _iswdigit_l((character), espeak_text_locale)
#define iswlower(character) _iswlower_l((character), espeak_text_locale)
#define iswpunct(character) _iswpunct_l((character), espeak_text_locale)
#define iswspace(character) _iswspace_l((character), espeak_text_locale)
#define iswupper(character) _iswupper_l((character), espeak_text_locale)
#define towlower(character) _towlower_l((character), espeak_text_locale)
#define towupper(character) _towupper_l((character), espeak_text_locale)

#endif
#endif
