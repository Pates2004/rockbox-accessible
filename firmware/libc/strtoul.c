/* Modified for Rockbox Accessible; change notice dated 2026-10-21. */
#include <stdlib.h>
#include <errno.h>
#include <ctype.h>
#include <limits.h>

unsigned long int strtoul(const char *ptr, char **endptr, int base)
{
    const char *cursor = ptr;
    unsigned long value = 0;
    int negative = 0;
    int overflow = 0;

    if (endptr)
        *endptr = (char *)ptr;
    if (base != 0 && (base < 2 || base > 36))
    {
        errno = EINVAL;
        return 0;
    }

    while (isspace((unsigned char)*cursor))
        ++cursor;
    if (*cursor == '+' || *cursor == '-')
    {
        negative = *cursor == '-';
        ++cursor;
    }

    if ((base == 0 || base == 16) && cursor[0] == '0' &&
        (cursor[1] == 'x' || cursor[1] == 'X') &&
        isxdigit((unsigned char)cursor[2]))
    {
        base = 16;
        cursor += 2;
    }
    else if (base == 0)
        base = *cursor == '0' ? 8 : 10;

    const char *digits = cursor;
    unsigned long cutoff = ULONG_MAX / base;
    unsigned int last_digit_limit = ULONG_MAX % base;

    for (;; ++cursor)
    {
        unsigned char character = (unsigned char)*cursor;
        unsigned int digit;
        if (character >= '0' && character <= '9')
            digit = character - '0';
        else if (character >= 'A' && character <= 'Z')
            digit = character - 'A' + 10;
        else if (character >= 'a' && character <= 'z')
            digit = character - 'a' + 10;
        else
            break;
        if (digit >= (unsigned int)base)
            break;

        if (!overflow)
        {
            if (value > cutoff ||
                (value == cutoff && digit > last_digit_limit))
                overflow = 1;
            else
                value = value * base + digit;
        }
    }

    if (cursor == digits)
    {
        errno = EINVAL;
        return 0;
    }
    if (endptr)
        *endptr = (char *)cursor;
    if (overflow)
    {
        errno = ERANGE;
        return ULONG_MAX;
    }
    return negative ? 0UL - value : value;
}
