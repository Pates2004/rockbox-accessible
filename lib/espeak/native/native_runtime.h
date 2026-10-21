#ifndef RB_ESPEAK_NATIVE_RUNTIME_H
#define RB_ESPEAK_NATIVE_RUNTIME_H

#include <stddef.h>
#include <stdint.h>
#include <stdarg.h>

#ifndef RB_ESPEAK_HEAP_BYTES
#define RB_ESPEAK_HEAP_BYTES (1536u * 1024u)
#endif
#define RB_ESPEAK_PATH_MAX 260
#define RB_ESPEAK_S_IFMT 0170000
#define RB_ESPEAK_S_IFREG 0100000
#define RB_ESPEAK_S_IFDIR 0040000

#ifdef __cplusplus
extern "C" {
#endif

typedef struct rb_espeak_FILE rb_espeak_FILE;
typedef struct rb_espeak_DIR rb_espeak_DIR;
struct rb_espeak_dirent { char d_name[RB_ESPEAK_PATH_MAX]; };
struct rb_espeak_stat { int64_t st_size; unsigned int st_mode; };
typedef struct rb_espeak_mbstate {
    unsigned char bytes[4];
    unsigned char count;
} rb_espeak_mbstate_t;
typedef void (*rb_espeak_yield_callback)(void *context);

extern int rb_espeak_errno;
extern rb_espeak_FILE * const rb_espeak_stdin;
extern rb_espeak_FILE * const rb_espeak_stdout;
extern rb_espeak_FILE * const rb_espeak_stderr;

int rb_espeak_engine_acquire(void);
void rb_espeak_engine_release(void);
int rb_espeak_engine_ready(void);
void rb_espeak_engine_mark_ready(void);
void rb_espeak_native_set_yield(rb_espeak_yield_callback callback, void *context);
void rb_espeak_native_yield(void);
size_t rb_espeak_heap_capacity(void);
size_t rb_espeak_heap_available(void);
size_t rb_espeak_heap_used(void);
size_t rb_espeak_heap_peak(void);
size_t rb_espeak_heap_failures(void);
void *rb_espeak_malloc(size_t size);
void *rb_espeak_calloc(size_t count, size_t size);
void *rb_espeak_realloc(void *memory, size_t size);
void rb_espeak_free(void *memory);

rb_espeak_FILE *rb_espeak_fopen(const char *path, const char *mode);
int rb_espeak_fclose(rb_espeak_FILE *stream);
size_t rb_espeak_fread(void *data, size_t size, size_t count, rb_espeak_FILE *stream);
int rb_espeak_fgetc(rb_espeak_FILE *stream);
int rb_espeak_ungetc(int character, rb_espeak_FILE *stream);
char *rb_espeak_fgets(char *data, int capacity, rb_espeak_FILE *stream);
int rb_espeak_fseek(rb_espeak_FILE *stream, long offset, int origin);
long rb_espeak_ftell(rb_espeak_FILE *stream);
void rb_espeak_rewind(rb_espeak_FILE *stream);
int rb_espeak_feof(rb_espeak_FILE *stream);
int rb_espeak_ferror(rb_espeak_FILE *stream);
void rb_espeak_clearerr(rb_espeak_FILE *stream);
size_t rb_espeak_fwrite(const void *data, size_t size, size_t count, rb_espeak_FILE *stream);
int rb_espeak_fputc(int character, rb_espeak_FILE *stream);
int rb_espeak_fputs(const char *text, rb_espeak_FILE *stream);
int rb_espeak_fflush(rb_espeak_FILE *stream);
int rb_espeak_vfprintf(rb_espeak_FILE *stream, const char *format, va_list arguments);
int rb_espeak_fprintf(rb_espeak_FILE *stream, const char *format, ...);
int rb_espeak_printf(const char *format, ...);
const char *rb_espeak_native_diagnostic(void);
int rb_espeak_stat(const char *path, struct rb_espeak_stat *details);
int rb_espeak_lstat(const char *path, struct rb_espeak_stat *details);
rb_espeak_DIR *rb_espeak_opendir(const char *path);
struct rb_espeak_dirent *rb_espeak_readdir(rb_espeak_DIR *directory);
int rb_espeak_closedir(rb_espeak_DIR *directory);

int rb_espeak_isalnum(int character);
int rb_espeak_isalpha(int character);
int rb_espeak_isblank(int character);
int rb_espeak_iscntrl(int character);
int rb_espeak_isdigit(int character);
int rb_espeak_isgraph(int character);
int rb_espeak_islower(int character);
int rb_espeak_isprint(int character);
int rb_espeak_ispunct(int character);
int rb_espeak_isspace(int character);
int rb_espeak_isupper(int character);
int rb_espeak_isxdigit(int character);
int rb_espeak_tolower(int character);
int rb_espeak_toupper(int character);
int rb_espeak_iswalnum(uint32_t character);
int rb_espeak_iswalpha(uint32_t character);
int rb_espeak_iswdigit(uint32_t character);
int rb_espeak_iswlower(uint32_t character);
int rb_espeak_iswpunct(uint32_t character);
int rb_espeak_iswspace(uint32_t character);
int rb_espeak_iswupper(uint32_t character);
uint32_t rb_espeak_towlower(uint32_t character);
uint32_t rb_espeak_towupper(uint32_t character);
size_t rb_espeak_wcslen(const wchar_t *text);
wchar_t *rb_espeak_wcschr(const wchar_t *text, wchar_t character);
wchar_t *rb_espeak_wcsncpy(wchar_t *destination, const wchar_t *source, size_t count);
int rb_espeak_wcsncmp(const wchar_t *left, const wchar_t *right, size_t count);
size_t rb_espeak_mbrtowc(wchar_t *out, const char *text, size_t size, rb_espeak_mbstate_t *state);
size_t rb_espeak_wcrtomb(char *out, wchar_t character, rb_espeak_mbstate_t *state);
int rb_espeak_mbsinit(const rb_espeak_mbstate_t *state);
int rb_espeak_mbtowc(wchar_t *out, const char *text, size_t size);
int rb_espeak_wctomb(char *out, wchar_t character);
size_t rb_espeak_mbstowcs(wchar_t *out, const char *text, size_t count);
size_t rb_espeak_wcstombs(char *out, const wchar_t *text, size_t count);
double rb_espeak_strtod(const char *text, char **end);
double rb_espeak_wcstod(const wchar_t *text, wchar_t **end);
double rb_espeak_atof(const char *text);
long rb_espeak_strtol(const char *text, char **end, int base);
unsigned long rb_espeak_strtoul(const char *text, char **end, int base);
size_t rb_espeak_strspn(const char *text, const char *accepted);
char *rb_espeak_strtok(char *text, const char *separators);
int rb_espeak_abs(int value);
char *rb_espeak_getenv(const char *name);
int rb_espeak_access(const char *path, int mode);
int rb_espeak_remove(const char *path);
unsigned int rb_espeak_sleep(unsigned int seconds);
int rb_espeak_usleep(unsigned long microseconds);
struct timespec;
int rb_espeak_nanosleep(const struct timespec *request, struct timespec *remaining);

#ifdef __cplusplus
}
#endif
#endif
