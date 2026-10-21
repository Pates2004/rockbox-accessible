#ifndef RB_ESPEAK_SHADOW_UNISTD_H
#define RB_ESPEAK_SHADOW_UNISTD_H
#include "native_only.h"
#include "../native_runtime.h"
#define F_OK 0
#define R_OK 4
#define W_OK 2
#define X_OK 1
#define access rb_espeak_access
#define sleep rb_espeak_sleep
#define usleep rb_espeak_usleep
#define nanosleep rb_espeak_nanosleep
#endif
