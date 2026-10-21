#include "rb_espeak.h"
#include "engine/speak_lib.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <locale.h>
#ifdef ESPEAK_DICTIONARY_WINDOWS_CASE_COMPAT
#include <cstdint>
#include <wctype.h>

static uint64_t georgian_case_inputs;

extern "C" int __real_iswupper(wint_t character);

extern "C" int __wrap_iswupper(wint_t character)
{
    if (character >= 0x1c90 && character <= 0x1cb0)
    {
        georgian_case_inputs |= UINT64_C(1) << (character - 0x1c90);
        return 0;
    }
    return __real_iswupper(character);
}
#endif
#ifdef _WIN32
#include "espeak_locale.h"
#endif

extern char path_home[150];
extern int CompileDictionary(const char *source, const char *name, FILE *log,
                             char *error_filename, int flags);

int main(int count, char **arguments)
{
    if (count != 4 || std::strlen(arguments[3]) >= sizeof(path_home))
        return 1;
#ifdef _WIN32
    espeak_text_locale = _create_locale(LC_CTYPE, "Polish_Poland.1250");
    if (!espeak_text_locale)
        return 1;
#else
    if (!setlocale(LC_CTYPE, "C.UTF-8"))
        return 1;
#endif
    if (rb_espeak_init(arguments[1]) != 22050 || espeak_SetVoiceByName("pl") != EE_OK)
        return 2;
    std::strcpy(path_home, arguments[3]);
    int errors = CompileDictionary(arguments[2], "pl", stderr, NULL, 0);
#ifdef _WIN32
    _free_locale(espeak_text_locale);
    espeak_text_locale = NULL;
#endif
    if (errors)
        return 3;
#ifdef ESPEAK_DICTIONARY_WINDOWS_CASE_COMPAT
    if (georgian_case_inputs != (UINT64_C(1) << 33) - 1)
        return 4;
    std::puts("PASS: exact 33 Georgian classifications match the supplied Windows compiler locale");
#endif
    std::puts("PASS: compiled supplied Polish dictionary sources into private output");
    return 0;
}
