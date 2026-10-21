#ifndef RB_ESPEAK_SHADOW_STAT_H
#define RB_ESPEAK_SHADOW_STAT_H
#include "../native_only.h"
#include "../../native_runtime.h"
#define stat rb_espeak_stat
#define lstat rb_espeak_lstat
#define S_IFMT RB_ESPEAK_S_IFMT
#define S_IFREG RB_ESPEAK_S_IFREG
#define S_IFDIR RB_ESPEAK_S_IFDIR
#define S_ISREG(mode) (((mode) & S_IFMT) == S_IFREG)
#define S_ISDIR(mode) (((mode) & S_IFMT) == S_IFDIR)
#endif
