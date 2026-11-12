# Accessibility service controls

Talkbox is the reader's interface name; its engine is still the supplied eSpeak
fork. These controls originated in ABI `0xe004` and are absent from older alpha10/Windows13
packages. New editions start in English with Talkbox and touch exploration off.
The optional Accessible-Polish.cfg selects Polish and enables these services.
Current development settings require matching ABI `0xe007` modules.
On Clip+ and Clip Zip, press and release Power three times quickly to toggle the
selected accessibility services. The shortcut is enabled in both supplied profiles.
With it enabled, one or two short clicks wait 300 ms after the last release, then
perform one native Power press/release sequence. This also works in settings and
the keyboard; unrelated buttons or a screen change cancel an unfinished group.
Holding Power and firmware emergency shutdown keep their separate input path.
Turn Use accessibility shortcut off to restore immediate ordinary Power input.
Windows maps Sansa Power to Escape; R1 Power is Insert.
New R1 profiles assign triple Power to the grouped shortcut in both interface
and playback profiles. Existing saved assignments are preserved. R1's supplied
ADC keyboard cannot reliably report both volume keys held together.

In Settings → General Settings → Accessibility → Talkbox settings, eSpeak settings
contains engine parameters only. The text reader and other Talkbox controls sit
alongside eSpeak settings within Talkbox settings.
Accessibility shortcut contains Use accessibility shortcut and Select
accessibility services. The shortcut is initially enabled and includes Talkbox
and touch exploration. Interface voice files and, where supported, Screen curtain
can also be included. Each service has its own inclusion switch; this selects
what the shortcut controls, rather than immediately changing that service.

If any selected service is off, invoking the shortcut enables all selected
services. If all are on, it disables them all. Disabling Talkbox also disables an
active screen curtain before speech is turned off, even if the curtain was not
selected. Enabling Talkbox can enable the curtain again only if the curtain is
selected and speech is available. Other unselected services retain their state.
One combined spoken status reports each selected service's resulting state and
any dependent curtain change, including when speech has just been turned off.
A partial failure is reported honestly; successful changes are not silently undone. An empty selection
or disabled shortcut changes nothing. No arbitrary two-service limit applies.

Assign Toggle accessibility shortcut services, Toggle Talkbox, Toggle interface
voice files or Turn touch browsing on or off independently:

- R1 physical buttons: Settings → General Settings → System → Physical button settings.
- Touchscreen gestures: Settings → General Settings → Accessibility → Touch exploration settings → Gesture assignments.

System contains Touchscreen settings and Physical button settings.
For touchscreen builds with eSpeak, Touchscreen settings moves from
Display to System. Touchscreen builds without eSpeak retain the Display entry.
Touch browsing and its gesture assignments remain in Accessibility.

The obsolete `/.rockbox/accessibility-shortcut.cfg` is ignored and left untouched.
Its old enabled/service values do not control either action. Assignments remain
in `/.rockbox/accessibility.cfg`; the normal eSpeak and voice-file preferences
remain independent.

Physical button settings and touchscreen gesture assignments retain the
independent service actions in addition to the group action. Existing
single/double/triple/hold mappings are preserved. Triple Power is a factory
assignment, not a forced overwrite of a saved Default or Unassigned slot.
Recognizing triple presses delays single/double Power until the click window
ends; hold Power and emergency recovery combinations remain separate.
Toggle actions execute once, not continuously
while a key is held. Disabled touch browsing does not recognize gestures; retain
a physical assignment if touch is your only other way to navigate.

Changing voice-file use never disables Talkbox or changes synthesized directory
and filename speech. Changing Talkbox does not alter voice-file preferences.
Turning voice files on while Talkbox is off requires a valid prerecorded voice
file matching the current Rockbox language/build. The test package does not
pretend to contain one. A missing file produces an error and restores the prior
voice-file preference. While Talkbox is on, voice-file use is an inactive
preference which can be changed independently.

Service changes request a synthesized enabled/disabled announcement even when
normal Talkbox is off or voice-file volume is zero. Speech still respects Talkbox
volume and the player's main volume; it never raises either. Missing/corrupt
engine data, unavailable output, zero volume or device failure can prevent
audible confirmation. An immediate failure to queue the status has a visual
fallback. Later synthesis or output failure, or zero volume, does not guarantee
a visual fallback or audible confirmation. Successful queuing is not proof that
physical audio was heard. Ordinary subsequent navigation can
interrupt a status announcement just as it interrupts other interface speech.

The gesture editor also contains triple tap, double tap and hold, optional held
stroke repeat, date/summary actions and launch destinations. These controls do
not establish physical touchscreen acceptance. Windows keyboard/PCM tests do not
verify an actual R1, NVDA, physical audio, radio operation or battery performance.

See [button controls](ACCESSIBILITY-BUTTONS.md),
[touch controls](ACCESSIBILITY-TOUCH.md) and
[R1 connectivity](HIBY-R1-CONNECTIVITY.md).
