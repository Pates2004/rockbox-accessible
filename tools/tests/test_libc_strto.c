#include <errno.h>
#include <limits.h>
#include <locale.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

long rb_strtol(const char *text, char **endptr, int base);
unsigned long rb_strtoul(const char *text, char **endptr, int base);

#ifdef TEST_ROCKBOX_LIBC
static int conversion_errno;

int *__errno(void)
{
    return &conversion_errno;
}
#else
#define conversion_errno errno
#endif

#ifndef EXPECT_LONG_BITS
#error Define EXPECT_LONG_BITS to validate the intended data model
#endif

typedef char long_width_check[sizeof(long) * CHAR_BIT == EXPECT_LONG_BITS ? 1 : -1];

static unsigned long checks;
static unsigned long failures;
static const char digits[] = "0123456789abcdefghijklmnopqrstuvwxyz";

static void check_signed(const char *text, int base, long expected,
                         size_t consumed, int expected_errno)
{
    const int initial_errors[] = {0, EDOM, ERANGE};
    for (size_t error_index = 0; error_index < 3; ++error_index)
    {
        for (int use_endptr = 0; use_endptr < 2; ++use_endptr)
        {
            char *endptr = NULL;
            conversion_errno = initial_errors[error_index];
            long actual = rb_strtol(text, use_endptr ? &endptr : NULL, base);
            int actual_errno = conversion_errno;
            int wanted_errno = expected_errno < 0 ? initial_errors[error_index]
                                                  : expected_errno;
            ++checks;
            if (actual != expected || actual_errno != wanted_errno ||
                (use_endptr && endptr != text + consumed))
            {
                if (failures++ < 20)
                    fprintf(stderr, "strtol base=%d text=[%s]: value=%ld/%ld "
                            "errno=%d/%d end=%ld/%lu initial=%d\n", base, text,
                            actual, expected, actual_errno, wanted_errno,
                            endptr ? (long)(endptr - text) : -1L,
                            (unsigned long)consumed, initial_errors[error_index]);
            }
        }
    }
}

static void check_unsigned(const char *text, int base, unsigned long expected,
                           size_t consumed, int expected_errno)
{
    const int initial_errors[] = {0, EDOM, ERANGE};
    for (size_t error_index = 0; error_index < 3; ++error_index)
    {
        for (int use_endptr = 0; use_endptr < 2; ++use_endptr)
        {
            char *endptr = NULL;
            conversion_errno = initial_errors[error_index];
            unsigned long actual = rb_strtoul(text, use_endptr ? &endptr : NULL, base);
            int actual_errno = conversion_errno;
            int wanted_errno = expected_errno < 0 ? initial_errors[error_index]
                                                  : expected_errno;
            ++checks;
            if (actual != expected || actual_errno != wanted_errno ||
                (use_endptr && endptr != text + consumed))
            {
                if (failures++ < 20)
                    fprintf(stderr, "strtoul base=%d text=[%s]: value=%lu/%lu "
                            "errno=%d/%d end=%ld/%lu initial=%d\n", base, text,
                            actual, expected, actual_errno, wanted_errno,
                            endptr ? (long)(endptr - text) : -1L,
                            (unsigned long)consumed, initial_errors[error_index]);
            }
        }
    }
}

static void check_both(const char *text, int base, long expected,
                       size_t consumed, int expected_errno)
{
    check_signed(text, base, expected, consumed, expected_errno);
    check_unsigned(text, base, (unsigned long)expected, consumed, expected_errno);
}

static void test_syntax(void)
{
    const char *empty_inputs[] = {"", " ", "\t\n\r\v\f", "+", "-", " -",
        " +", "++1", "--1", "+-1", "-+1", "+ 1", "- 1", "xyz", ".1", "/1",
        ":1", "@1", "[1", "`1", "{1", "\x80", "\xff", " \xff"};
    for (size_t index = 0; index < sizeof(empty_inputs) / sizeof(empty_inputs[0]); ++index)
        check_both(empty_inputs[index], 10, 0, 0, EINVAL);

    const int invalid_bases[] = {INT_MIN, -36, -1, 1, 37, 256, INT_MAX};
    for (size_t index = 0; index < sizeof(invalid_bases) / sizeof(invalid_bases[0]); ++index)
    {
        check_both("  -123", invalid_bases[index], 0, 0, EINVAL);
        check_both("", invalid_bases[index], 0, 0, EINVAL);
    }

    check_both(" \t\n\r\v\f-42!", 10, -42, 9, -1);
    check_both("  +42!", 10, 42, 5, -1);
    check_both("-0", 0, 0, 2, -1);
    check_both("+0", 0, 0, 2, -1);
    check_both("000", 0, 0, 3, -1);
    check_both("077!", 0, 63, 3, -1);
    check_both("08", 0, 0, 1, -1);
    check_both("09", 8, 0, 1, -1);
    check_both("08", 10, 8, 2, -1);
    check_both("8", 8, 0, 0, EINVAL);
    check_both("0x", 0, 0, 1, -1);
    check_both("0X", 16, 0, 1, -1);
    check_both("0xg", 16, 0, 1, -1);
    check_both("-0x", 0, 0, 2, -1);
    check_both("+0xg", 16, 0, 2, -1);
    check_both("0x+1", 0, 0, 1, -1);
    check_both("0x 1", 16, 0, 1, -1);
    check_both("0x1f!", 0, 31, 4, -1);
    check_both("-0XfF!", 16, -255, 5, -1);
    check_both("0x10", 10, 0, 1, -1);
    check_both("0x10", 8, 0, 1, -1);
    check_both("0x10", 36, 42804, 4, -1);
    check_both("0b10", 0, 0, 1, -1);
    check_both("0b10", 2, 0, 1, -1);
    check_both("zZ!", 36, 1295, 2, -1);
    check_both("Z", 35, 0, 0, EINVAL);
    check_both("1012", 2, 5, 3, -1);
    check_both("123 4", 10, 123, 3, -1);
    check_both("12\0ignored", 10, 12, 2, -1);
    check_both("12\xff", 10, 12, 2, -1);
}

static void encode_number(char *output, unsigned long long number, int base)
{
    char reversed[sizeof(number) * CHAR_BIT];
    size_t length = 0;
    do
    {
        reversed[length++] = digits[number % (unsigned int)base];
        number /= (unsigned int)base;
    } while (number);
    for (size_t index = 0; index < length; ++index)
        output[index] = reversed[length - index - 1];
    output[length] = '\0';
}

static void increment_number(char *text, int base)
{
    size_t length = strlen(text);
    size_t position = length;
    while (position > 0)
    {
        --position;
        int digit = (int)(strchr(digits, text[position]) - digits);
        if (++digit < base)
        {
            text[position] = digits[digit];
            return;
        }
        text[position] = '0';
    }
    memmove(text + 1, text, length + 1);
    text[0] = '1';
}

static void test_extrema(void)
{
    const unsigned long long signed_limit = (unsigned long long)LONG_MAX;
    const unsigned long long negative_limit = 0ULL - (unsigned long long)LONG_MIN;
    char text[256];
    char negative[260];
    for (int base = 2; base <= 36; ++base)
    {
        const unsigned long long values[] = {0, 1, signed_limit - 1, signed_limit,
            signed_limit + 1, negative_limit, negative_limit + 1,
            (unsigned long long)ULONG_MAX - 1, ULONG_MAX};
        for (size_t index = 0; index < sizeof(values) / sizeof(values[0]); ++index)
        {
            unsigned long long value = values[index];
            encode_number(text, value, base);
            size_t length = strlen(text);
            strcat(text, "!");
            check_unsigned(text, base, (unsigned long)value, length, -1);
            check_signed(text, base, value <= signed_limit ? (long)value : LONG_MAX,
                         length, value <= signed_limit ? -1 : ERANGE);
            snprintf(negative, sizeof(negative), "-%s", text);
            check_unsigned(negative, base, 0UL - (unsigned long)value, length + 1, -1);
            long expected = value >= negative_limit ? LONG_MIN : -(long)value;
            check_signed(negative, base, expected, length + 1,
                         value <= negative_limit ? -1 : ERANGE);
        }

        encode_number(text, ULONG_MAX, base);
        increment_number(text, base);
        size_t length = strlen(text);
        strcat(text, "!");
        check_unsigned(text, base, ULONG_MAX, length, ERANGE);
        check_signed(text, base, LONG_MAX, length, ERANGE);
        snprintf(negative, sizeof(negative), "-%s", text);
        check_unsigned(negative, base, ULONG_MAX, length + 1, ERANGE);
        check_signed(negative, base, LONG_MIN, length + 1, ERANGE);

        memset(text, '1', 200);
        text[200] = '!';
        text[201] = '\0';
        check_unsigned(text, base, ULONG_MAX, 200, ERANGE);
        check_signed(text, base, LONG_MAX, 200, ERANGE);
        snprintf(negative, sizeof(negative), "-%s", text);
        check_unsigned(negative, base, ULONG_MAX, 201, ERANGE);
        check_signed(negative, base, LONG_MIN, 201, ERANGE);
    }
}

static void test_byte_classification(void)
{
    char text[4];
    for (unsigned int character = 1; character <= UCHAR_MAX; ++character)
    {
        int digit = 36;
        if (character >= '0' && character <= '9')
            digit = character - '0';
        if (character >= 'a' && character <= 'z')
            digit = character - 'a' + 10;
        if (character >= 'A' && character <= 'Z')
            digit = character - 'A' + 10;
        text[0] = (char)character;
        text[1] = '\0';
        for (int base = 2; base <= 36; ++base)
            check_both(text, base, digit < base ? digit : 0,
                       digit < base ? 1 : 0, digit < base ? -1 : EINVAL);

        text[0] = '0';
        text[1] = 'x';
        text[2] = (char)character;
        text[3] = '\0';
        check_both(text, 0, digit < 16 ? digit : 0, digit < 16 ? 3 : 1, -1);
        check_both(text, 16, digit < 16 ? digit : 0, digit < 16 ? 3 : 1, -1);
    }
}

static void test_prefixed_extrema(void)
{
    const int bases[] = {8, 10, 16};
    const char *prefixes[] = {"0", "", "0X"};
    const char *signs[] = {"", "+", "-"};
    const unsigned long values[] = {LONG_MAX, (unsigned long)LONG_MAX + 1, ULONG_MAX};
    unsigned long negative_limit = 0UL - (unsigned long)LONG_MIN;
    char number[sizeof(long) * CHAR_BIT + 1];
    char text[sizeof(long) * CHAR_BIT + 32];
    for (size_t base_index = 0; base_index < 3; ++base_index)
    {
        for (size_t sign_index = 0; sign_index < 3; ++sign_index)
        {
            for (size_t value_index = 0; value_index < 3; ++value_index)
            {
                unsigned long value = values[value_index];
                encode_number(number, value, bases[base_index]);
                snprintf(text, sizeof(text), " \t%s%s000%s!",
                         signs[sign_index], prefixes[base_index], number);
                size_t length = strlen(text) - 1;
                int negative = sign_index == 2;
                int overflow = value > (negative ? negative_limit : (unsigned long)LONG_MAX);
                long expected = value > (unsigned long)LONG_MAX ? LONG_MAX : (long)value;
                if (negative)
                    expected = value >= negative_limit ? LONG_MIN : -(long)value;
                for (int autodetect = 0; autodetect < 2; ++autodetect)
                {
                    int base = autodetect ? 0 : bases[base_index];
                    if (autodetect && base_index == 1)
                        continue;
                    check_signed(text, base, expected, length, overflow ? ERANGE : -1);
                    check_unsigned(text, base, negative ? 0UL - value : value, length, -1);
                }
            }
        }
    }

    const char *short_inputs[] = {"", "+", "-", "0", "0x", "-0X", " +0Xg"};
    const size_t consumed[] = {0, 0, 0, 1, 1, 2, 3};
    for (size_t index = 0; index < sizeof(consumed) / sizeof(consumed[0]); ++index)
    {
        size_t length = strlen(short_inputs[index]) + 1;
        char *allocated = malloc(length);
        if (!allocated)
            exit(2);
        memcpy(allocated, short_inputs[index], length);
        check_both(allocated, 0, 0, consumed[index], consumed[index] ? -1 : EINVAL);
        check_both(allocated, 16, 0, consumed[index], consumed[index] ? -1 : EINVAL);
        free(allocated);
    }
}

#ifndef TEST_NO_HOST_DIFFERENTIAL
static uint32_t random_state = UINT32_C(0x73ca5019);

static uint32_t next_random(void)
{
    random_state = random_state * UINT32_C(1664525) + UINT32_C(1013904223);
    return random_state;
}

static void compare_host(const char *text, int base)
{
    char *endptr;
    errno = EDOM;
    long signed_value = strtol(text, &endptr, base);
    int expected_errno = endptr == text ? EINVAL : errno == EDOM ? -1 : errno;
    check_signed(text, base, signed_value, (size_t)(endptr - text), expected_errno);
    errno = EDOM;
    unsigned long unsigned_value = strtoul(text, &endptr, base);
    expected_errno = endptr == text ? EINVAL : errno == EDOM ? -1 : errno;
    check_unsigned(text, base, unsigned_value, (size_t)(endptr - text), expected_errno);
}

static void test_differential(void)
{
    static const unsigned char alphabet[] = "0123456789abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ +-\t\n\r\v\f!:/@[`{\x80\xff";
    char text[192];
    for (int base_index = 0; base_index < 36; ++base_index)
    {
        int base = base_index == 0 ? 0 : base_index + 1;
        for (unsigned int character = 1; character <= UCHAR_MAX; ++character)
        {
            text[0] = (char)character;
            text[1] = '\0';
            compare_host(text, base);
            text[0] = '0';
            text[1] = 'x';
            text[2] = (char)character;
            text[3] = '\0';
            compare_host(text, base);
        }
    }
    for (unsigned int trial = 0; trial < 100000; ++trial)
    {
        unsigned int base_index = next_random() % 36;
        int base = base_index == 0 ? 0 : (int)base_index + 1;
        size_t length = next_random() % sizeof(text);
        for (size_t index = 0; index < length; ++index)
            text[index] = (char)alphabet[next_random() % (sizeof(alphabet) - 1)];
        text[length] = '\0';
        compare_host(text, base);
    }
}
#endif

int main(void)
{
    if (!setlocale(LC_ALL, "C"))
        return 2;
    test_syntax();
    test_extrema();
    test_byte_classification();
    test_prefixed_extrema();
#ifndef TEST_NO_HOST_DIFFERENTIAL
    test_differential();
#endif
    printf("%s: %lu checks, %lu failures, %d-bit long\n",
           failures ? "FAIL" : "PASS", checks, failures, EXPECT_LONG_BITS);
    return failures ? 1 : 0;
}
