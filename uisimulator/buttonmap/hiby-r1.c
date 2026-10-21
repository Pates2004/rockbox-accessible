/*
 * HiBy R1 simulator-map reference: bahusoid/rockbox,
 * commit 059809d123a5b2d4ff1d65b571e99cf56b35dd51, same source path.
 * Original simulator map: Copyright (C) 2021 by Solomon Peachy.
 * Original terms: GNU General Public License, version 2 or any later version;
 * distributed on an AS IS basis, WITHOUT WARRANTY OF ANY KIND.
 * Reworked keyboard mapping for Rockbox Accessible;
 * change notice dated 2026-10-21. See docs/COPYING for the license.
 */
#include <SDL.h>
#include "button.h"
#include "buttonmap.h"

int key_to_button(int keyboard_button)
{
    switch (keyboard_button)
    {
        case SDLK_UP:
        case SDLK_KP_8:
            return BUTTON_VOL_UP;
        case SDLK_DOWN:
        case SDLK_KP_2:
            return BUTTON_VOL_DOWN;
        case SDLK_RIGHT:
        case SDLK_RETURN:
        case SDLK_KP_ENTER:
            return BUTTON_NEXT;
        case SDLK_LEFT:
        case SDLK_BACKSPACE:
            return BUTTON_PLAY;
        case SDLK_SPACE:
        case SDLK_INSERT:
        case SDLK_ESCAPE:
            return BUTTON_POWER;
        default:
            return BUTTON_NONE;
    }
}

struct button_map bm[] = {
    { SDLK_UP, 0, 0, 0, "Volume up" },
    { SDLK_DOWN, 0, 0, 0, "Volume down" },
    { SDLK_RETURN, 0, 0, 0, "Next" },
    { SDLK_BACKSPACE, 0, 0, 0, "Play" },
    { SDLK_SPACE, 0, 0, 0, "Power" },
    { 0, 0, 0, 0, "None" }
};
