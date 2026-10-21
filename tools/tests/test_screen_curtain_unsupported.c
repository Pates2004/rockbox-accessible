#include "screen_curtain_fixture.h"
#include "../../firmware/export/backlight.h"
#include "../../firmware/backlight.c"

#ifdef HAVE_SCREEN_CURTAIN
#error Unsupported target advertises screen curtain capability
#endif

int main(void)
{
    assert(!backlight_screen_curtain_active());
    backlight_set_screen_curtain(true);
    assert(!backlight_screen_curtain_active());
    backlight_set_screen_curtain(false);
    assert(!backlight_screen_curtain_active());
    return 0;
}
