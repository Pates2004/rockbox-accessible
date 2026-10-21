# Screen curtain

Open **Settings → General Settings → Accessibility → Talkbox settings → Screen settings → Screen curtain**. You can
also assign **Screen curtain** to a gesture or physical button. It toggles black
display output without stopping speech, music or touch navigation. Talkbox must
have an available eSpeak engine before enabling it. Disabling Talkbox restores the screen on the
next core input dispatch, rather than leaving a silent invisible interface.

The curtain does not overwrite brightness, normal backlight timeouts, gesture
assignments or the screen-lock setting. Normal button activity and charging
events must not reveal the core screen while it is enabled. Screen lock remains
a separate feature: ordinary reader gestures cannot unlock a locked screen.
Optional System touch-wake assignments are a separate explicit exception; they
do not disable the curtain. See [screen policies](ACCESSIBILITY-SCREEN.md).

On R1, while the curtain is active, **Power + Next** restores the screen before
custom mappings or softlock handling. Release both keys before continuing;
neither component release should activate an item. With the curtain off, the
same chord retains its normal contextual function. The recovery chord is handled
by the shared action API and the standard plugin `button_get`/`button_get_w_tmo`
callbacks. A plugin polling only button status, or bypassing these APIs, can
still bypass the recovery chord.
The existing physical Power emergency shutdown is not disabled. Restarting
Rockbox always starts with the curtain off; a black startup state is deliberately
not persisted. This also provides recovery from a raw-input plugin.

This is not a device-wide privacy guarantee. The boot selector, factory system,
kernel, panic/recovery screens and external programs are outside the curtain.
Native R1 framebuffer and Windows simulator display paths need separate tests;
host mocks cannot establish physical screen brightness or power savings. Other
target display backends require their own integration and verification.
