#ifndef ROCKBOX_ACCESSIBILITY_SHORTCUT_H
#define ROCKBOX_ACCESSIBILITY_SHORTCUT_H

#include <stdbool.h>

bool accessibility_shortcut_toggle_espeak(void);
bool accessibility_shortcut_toggle_voice_files(void);
bool accessibility_shortcut_set_espeak(bool enabled);
bool accessibility_shortcut_set_voice_files(bool enabled);

#endif
