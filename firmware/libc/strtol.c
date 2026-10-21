/* Modified for Rockbox Accessible; change notice dated 2026-10-21. */
#include <stdlib.h>
#include <errno.h>
#include <limits.h>
#include <ctype.h>

long int strtol(const char *ptr, char **endptr, int base)
{
    const char *cursor = ptr;
    long value = 0;
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
    long limit = negative ? LONG_MIN : -LONG_MAX;
    long cutoff = limit / base;
    int last_digit_limit = -(limit % base);

    for (;; ++cursor)
    {
        unsigned char character = (unsigned char)*cursor;
        int digit;
        if (character >= '0' && character <= '9')
            digit = character - '0';
        else if (character >= 'A' && character <= 'Z')
            digit = character - 'A' + 10;
        else if (character >= 'a' && character <= 'z')
            digit = character - 'a' + 10;
        else
            break;
        if (digit >= base)
            break;

        if (!overflow)
        {
            if (value < cutoff ||
                (value == cutoff && digit > last_digit_limit))
                overflow = 1;
            else
                value = value * base - digit;
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
        return negative ? LONG_MIN : LONG_MAX;
    }
    return negative ? value : -value;
}
