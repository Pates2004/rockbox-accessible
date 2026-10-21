#include "native_runtime.h"
#include "../../utf8proc/utf8proc.h"
#include "native_errno.h"
#include <float.h>
#include <limits.h>
#include <stdlib.h>
#include <string.h>

#ifdef RB_ESPEAK_SHADOW_STDLIB_H
#error Compile native adapter C with ordinary Rockbox headers, not eSpeak shadow headers
#endif

int rb_espeak_isupper(int character) { return character >= 'A' && character <= 'Z'; }
int rb_espeak_islower(int character) { return character >= 'a' && character <= 'z'; }
int rb_espeak_isalpha(int character) { return rb_espeak_isupper(character) || rb_espeak_islower(character); }
int rb_espeak_isdigit(int character) { return character >= '0' && character <= '9'; }
int rb_espeak_isalnum(int character) { return rb_espeak_isalpha(character) || rb_espeak_isdigit(character); }
int rb_espeak_isblank(int character) { return character == ' ' || character == '\t'; }
int rb_espeak_isspace(int character) { return character == ' ' || (character >= '\t' && character <= '\r'); }
int rb_espeak_iscntrl(int character) { return (character >= 0 && character < 32) || character == 127; }
int rb_espeak_isprint(int character) { return character >= 32 && character <= 126; }
int rb_espeak_isgraph(int character) { return character >= 33 && character <= 126; }
int rb_espeak_ispunct(int character) { return rb_espeak_isgraph(character) && !rb_espeak_isalnum(character); }
int rb_espeak_isxdigit(int character)
{
    return rb_espeak_isdigit(character) || (character >= 'a' && character <= 'f') ||
           (character >= 'A' && character <= 'F');
}
int rb_espeak_tolower(int character) { return rb_espeak_isupper(character) ? character + ('a' - 'A') : character; }
int rb_espeak_toupper(int character) { return rb_espeak_islower(character) ? character - ('a' - 'A') : character; }

static int scalar(uint32_t character)
{
    return character <= 0x10ffff && !(character >= 0xd800 && character <= 0xdfff);
}

static utf8proc_category_t category(uint32_t character)
{
    return scalar(character) ? utf8proc_category((int32_t)character) : UTF8PROC_CATEGORY_CN;
}

int rb_espeak_iswalpha(uint32_t character)
{
    utf8proc_category_t kind = category(character);
    return (kind >= UTF8PROC_CATEGORY_LU && kind <= UTF8PROC_CATEGORY_LO) || kind == UTF8PROC_CATEGORY_NL;
}
int rb_espeak_iswdigit(uint32_t character) { return category(character) == UTF8PROC_CATEGORY_ND; }
int rb_espeak_iswalnum(uint32_t character) { return rb_espeak_iswalpha(character) || rb_espeak_iswdigit(character); }
int rb_espeak_iswlower(uint32_t character)
{
    return scalar(character) && utf8proc_islower((int32_t)character);
}
int rb_espeak_iswupper(uint32_t character)
{
    return scalar(character) && utf8proc_isupper((int32_t)character);
}
int rb_espeak_iswpunct(uint32_t character)
{
    utf8proc_category_t kind = category(character);
    return kind >= UTF8PROC_CATEGORY_PC && kind <= UTF8PROC_CATEGORY_SO;
}
int rb_espeak_iswspace(uint32_t character)
{
    utf8proc_category_t kind = category(character);
    return (character >= 9 && character <= 13) || character == 0x85 ||
           (kind >= UTF8PROC_CATEGORY_ZS && kind <= UTF8PROC_CATEGORY_ZP);
}
uint32_t rb_espeak_towlower(uint32_t character)
{
    return scalar(character) ? (uint32_t)utf8proc_tolower((int32_t)character) : character;
}
uint32_t rb_espeak_towupper(uint32_t character)
{
    return scalar(character) ? (uint32_t)utf8proc_toupper((int32_t)character) : character;
}

size_t rb_espeak_wcslen(const wchar_t *text)
{
    const wchar_t *end = text;
    while (*end)
        ++end;
    return (size_t)(end - text);
}
wchar_t *rb_espeak_wcschr(const wchar_t *text, wchar_t character)
{
    do
    {
        if (*text == character)
            return (wchar_t *)text;
    } while (*text++);
    return NULL;
}
wchar_t *rb_espeak_wcsncpy(wchar_t *destination, const wchar_t *source, size_t count)
{
    size_t index = 0;
    while (index < count && source[index])
    {
        destination[index] = source[index];
        ++index;
    }
    while (index < count)
        destination[index++] = 0;
    return destination;
}
int rb_espeak_wcsncmp(const wchar_t *left, const wchar_t *right, size_t count)
{
    while (count--)
    {
        if (*left != *right)
            return *left < *right ? -1 : 1;
        if (!*left)
            break;
        ++left;
        ++right;
    }
    return 0;
}

static rb_espeak_mbstate_t implicit_decode_state;

static size_t invalid_sequence(rb_espeak_mbstate_t *state)
{
    memset(state, 0, sizeof(*state));
    rb_espeak_errno = EILSEQ;
    return (size_t)-1;
}

size_t rb_espeak_mbrtowc(wchar_t *out, const char *text, size_t size, rb_espeak_mbstate_t *state)
{
    size_t consumed = 0;
    unsigned int needed;
    unsigned int first;
    utf8proc_int32_t character;
    if (!state)
        state = &implicit_decode_state;
    if (!text)
    {
        text = "";
        size = 1;
        out = NULL;
    }
    if (state->count > 3)
        return invalid_sequence(state);
    if (!size)
        return (size_t)-2;
    if (!state->count)
        state->bytes[state->count++] = (unsigned char)text[consumed++];
    first = state->bytes[0];
    if (first < 0x80)
        needed = 1;
    else if (first >= 0xc2 && first <= 0xdf)
        needed = 2;
    else if (first >= 0xe0 && first <= 0xef)
        needed = 3;
    else if (first >= 0xf0 && first <= 0xf4)
        needed = 4;
    else
        return invalid_sequence(state);
    while (state->count < needed && consumed < size)
    {
        unsigned int next = (unsigned char)text[consumed++];
        if (next < 0x80 || next > 0xbf ||
            (state->count == 1 && ((first == 0xe0 && next < 0xa0) ||
             (first == 0xed && next > 0x9f) || (first == 0xf0 && next < 0x90) ||
             (first == 0xf4 && next > 0x8f))))
            return invalid_sequence(state);
        state->bytes[state->count++] = (unsigned char)next;
    }
    if (state->count < needed)
        return (size_t)-2;
    if (utf8proc_iterate(state->bytes, needed, &character) < 0)
        return invalid_sequence(state);
    memset(state, 0, sizeof(*state));
    if (out)
        *out = (wchar_t)character;
    return character ? consumed : 0;
}

size_t rb_espeak_wcrtomb(char *out, wchar_t character, rb_espeak_mbstate_t *state)
{
    if (state)
        memset(state, 0, sizeof(*state));
    if (!out)
        return 1;
    if (!scalar((uint32_t)character))
    {
        rb_espeak_errno = EILSEQ;
        return (size_t)-1;
    }
    return (size_t)utf8proc_encode_char((int32_t)character, (unsigned char *)out);
}
int rb_espeak_mbsinit(const rb_espeak_mbstate_t *state) { return !state || !state->count; }
int rb_espeak_mbtowc(wchar_t *out, const char *text, size_t size)
{
    rb_espeak_mbstate_t state = { { 0 }, 0 };
    size_t result;
    if (!text)
        return 0;
    result = rb_espeak_mbrtowc(out, text, size, &state);
    if (result == (size_t)-2)
        rb_espeak_errno = EILSEQ;
    return result >= (size_t)-2 ? -1 : (int)result;
}
int rb_espeak_wctomb(char *out, wchar_t character)
{
    if (!out)
        return 0;
    return (int)rb_espeak_wcrtomb(out, character, NULL);
}
size_t rb_espeak_mbstowcs(wchar_t *out, const char *text, size_t count)
{
    size_t converted = 0;
    while (!out || converted < count)
    {
        size_t available = 0;
        wchar_t character;
        int consumed;
        while (available < 4 && text[available])
            ++available;
        consumed = rb_espeak_mbtowc(&character, text, available ? available : 1);
        if (consumed < 0)
            return (size_t)-1;
        if (out)
            out[converted] = character;
        if (!consumed)
            return converted;
        ++converted;
        text += consumed;
    }
    return converted;
}
size_t rb_espeak_wcstombs(char *out, const wchar_t *text, size_t count)
{
    size_t converted = 0;
    while (!out || converted < count)
    {
        char encoded[4];
        size_t length = rb_espeak_wcrtomb(encoded, *text, NULL);
        if (length == (size_t)-1)
            return (size_t)-1;
        if (out && length > count - converted)
            break;
        if (out)
            memcpy(out + converted, encoded, length);
        if (!*text++)
            return converted;
        converted += length;
    }
    return converted;
}

static unsigned int number_character(const void *text, size_t index, int wide)
{
    return wide ? (unsigned int)((const wchar_t *)text)[index] : ((const unsigned char *)text)[index];
}

static int match_number_token(const void *text, size_t index, int wide, const char *token)
{
    while (*token)
    {
        if (rb_espeak_tolower((int)number_character(text, index++, wide)) != *token++)
            return 0;
    }
    return 1;
}

static int number_digit(unsigned int character, int radix)
{
    if (character >= '0' && character <= '9')
        return (int)(character - '0');
    if (radix == 16)
    {
        character = (unsigned int)rb_espeak_tolower((int)character);
        if (character >= 'a' && character <= 'f')
            return (int)(character - 'a' + 10);
    }
    return -1;
}

static double parse_number(const void *text, size_t *end, int wide)
{
    size_t index = 0;
    int negative = 0;
    int radix = 10;
    int fractional = 0;
    int digits = 0;
    int significant = 0;
    int exponent = 0;
    int exponent_unit = 1;
    double value = 0;
    unsigned int character;
    *end = 0;
    while (rb_espeak_isspace((int)number_character(text, index, wide)))
        ++index;
    character = number_character(text, index, wide);
    if (character == '-' || character == '+')
    {
        negative = character == '-';
        ++index;
    }
    if (match_number_token(text, index, wide, "inf"))
    {
        index += 3;
        if (match_number_token(text, index, wide, "inity"))
            index += 5;
        *end = index;
        return negative ? -__builtin_huge_val() : __builtin_huge_val();
    }
    if (match_number_token(text, index, wide, "nan"))
    {
        index += 3;
        if (number_character(text, index, wide) == '(')
        {
            size_t tail = index + 1;
            while (rb_espeak_isalnum((int)number_character(text, tail, wide)) || number_character(text, tail, wide) == '_')
                ++tail;
            if (number_character(text, tail, wide) == ')')
                index = tail + 1;
        }
        *end = index;
        return negative ? -__builtin_nan("") : __builtin_nan("");
    }
    if (number_character(text, index, wide) == '0' &&
        rb_espeak_tolower((int)number_character(text, index + 1, wide)) == 'x')
    {
        unsigned int next = number_character(text, index + 2, wide);
        if (number_digit(next, 16) >= 0 || (next == '.' && number_digit(number_character(text, index + 3, wide), 16) >= 0))
        {
            radix = 16;
            exponent_unit = 4;
            index += 2;
        }
    }
    for (;; ++index)
    {
        int digit;
        character = number_character(text, index, wide);
        if (character == '.' && !fractional)
        {
            fractional = 1;
            continue;
        }
        digit = number_digit(character, radix);
        if (digit < 0)
            break;
        digits = 1;
        if (significant < (radix == 16 ? 13 : 17))
        {
            value = value * radix + digit;
            if (value)
                ++significant;
            if (fractional && exponent > -1000000)
                exponent -= exponent_unit;
        }
        else if (!fractional && exponent < 1000000)
            exponent += exponent_unit;
    }
    if (!digits)
        return 0;
    if (rb_espeak_tolower((int)character) == (radix == 16 ? 'p' : 'e'))
    {
        size_t marker = index++;
        int exponent_negative = 0;
        int explicit_exponent = 0;
        character = number_character(text, index, wide);
        if (character == '-' || character == '+')
        {
            exponent_negative = character == '-';
            ++index;
        }
        if (!rb_espeak_isdigit((int)number_character(text, index, wide)))
            index = marker;
        else
        {
            while (rb_espeak_isdigit((int)(character = number_character(text, index, wide))))
            {
                if (explicit_exponent < 1000000)
                    explicit_exponent = explicit_exponent * 10 + (int)(character - '0');
                ++index;
            }
            exponent += exponent_negative ? -explicit_exponent : explicit_exponent;
        }
    }
    *end = index;
    if (value)
    {
        int limit = radix == 16 ? 1200 : 400;
        double factor = radix == 16 ? 2.0 : 10.0;
        if (exponent > limit)
            value = __builtin_huge_val();
        else if (exponent < -limit)
            value = 0;
        else
        {
            while (exponent > 0)
            {
                if (value > DBL_MAX / factor)
                {
                    value = __builtin_huge_val();
                    break;
                }
                value *= factor;
                --exponent;
            }
            while (exponent < 0)
            {
                value /= factor;
                ++exponent;
            }
        }
        if (value > DBL_MAX || value < DBL_MIN)
            rb_espeak_errno = ERANGE;
    }
    return negative ? -value : value;
}

double rb_espeak_strtod(const char *text, char **end)
{
    size_t consumed;
    double result = parse_number(text, &consumed, 0);
    if (end)
        *end = (char *)text + consumed;
    return result;
}
double rb_espeak_wcstod(const wchar_t *text, wchar_t **end)
{
    size_t consumed;
    double result = parse_number(text, &consumed, 1);
    if (end)
        *end = (wchar_t *)text + consumed;
    return result;
}
double rb_espeak_atof(const char *text) { return rb_espeak_strtod(text, NULL); }
long rb_espeak_strtol(const char *text, char **end, int base)
{
    long result;
    errno = 0;
    result = strtol(text, end, base);
    if (errno)
        rb_espeak_errno = errno;
    return result;
}
unsigned long rb_espeak_strtoul(const char *text, char **end, int base)
{
    unsigned long result;
    errno = 0;
    result = strtoul(text, end, base);
    if (errno)
        rb_espeak_errno = errno;
    return result;
}

size_t rb_espeak_strspn(const char *text, const char *accepted)
{
    size_t count = 0;
    while (text[count] && strchr(accepted, (unsigned char)text[count]))
        ++count;
    return count;
}

char *rb_espeak_strtok(char *text, const char *separators)
{
    static char *next;
    char *token;
    if (text)
        next = text;
    if (!next)
        return NULL;
    next += rb_espeak_strspn(next, separators);
    if (!*next)
    {
        next = NULL;
        return NULL;
    }
    token = next;
    while (*next && !strchr(separators, (unsigned char)*next))
        ++next;
    if (*next)
        *next++ = 0;
    else
        next = NULL;
    return token;
}

int rb_espeak_abs(int value)
{
    if (value == INT_MIN)
    {
        rb_espeak_errno = ERANGE;
        return INT_MAX;
    }
    return value < 0 ? -value : value;
}
