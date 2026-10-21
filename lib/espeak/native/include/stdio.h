#ifndef RB_ESPEAK_SHADOW_STDIO_H
#define RB_ESPEAK_SHADOW_STDIO_H
#include "native_only.h"
#include "../native_runtime.h"
#define FILE rb_espeak_FILE
#define EOF (-1)
#define SEEK_SET 0
#define SEEK_CUR 1
#define SEEK_END 2
#define stdin rb_espeak_stdin
#define stdout rb_espeak_stdout
#define stderr rb_espeak_stderr
#define fopen rb_espeak_fopen
#define fclose rb_espeak_fclose
#define fread rb_espeak_fread
#define fwrite rb_espeak_fwrite
#define fgetc rb_espeak_fgetc
#define getc rb_espeak_fgetc
#define ungetc rb_espeak_ungetc
#define fgets rb_espeak_fgets
#define fputc rb_espeak_fputc
#define putc rb_espeak_fputc
#define fputs rb_espeak_fputs
#define fseek rb_espeak_fseek
#define ftell rb_espeak_ftell
#define rewind rb_espeak_rewind
#define feof rb_espeak_feof
#define ferror rb_espeak_ferror
#define clearerr rb_espeak_clearerr
#define fflush rb_espeak_fflush
#define fprintf rb_espeak_fprintf
#define vfprintf rb_espeak_vfprintf
#define printf rb_espeak_printf
#define remove rb_espeak_remove
#ifdef __cplusplus
extern "C" {
#endif
int snprintf(char *buffer, size_t size, const char *format, ...);
int vsnprintf(char *buffer, size_t size, const char *format, va_list arguments);
int sprintf(char *buffer, const char *format, ...);
int sscanf(const char *text, const char *format, ...);
#ifdef __cplusplus
}
#endif
#endif
