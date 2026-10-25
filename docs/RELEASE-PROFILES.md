# Release profiles

[Polski](RELEASE-PROFILES-PL.md)

New integrated builds start in English with Talkbox and touch exploration off.
The accessibility shortcut remains enabled and selects Talkbox and supported
touch exploration. Fresh HiBy R1 interface and playback mappings use **three
quick Power presses**. Turning off exploration does not disable that physical
shortcut. Existing saved settings and custom mappings remain in effect.
Other ports retain their capability limits; an R1 input test is not confirmation
of another player's Power button or touchscreen.

`Accessible-Polish.cfg` is an optional profile, not an automatically loaded
default. It selects Polish, enables Talkbox and supported touch exploration,
and keeps the same shortcut service selection. It does not reset customized
button mappings. eSpeak follows the UI language.

For the Windows simulator, copy the provided CFG into `simdisk`, beside
`.rockbox`, then open it through **Files**. On a native card the optional CFG
is supplied under `.rockbox`; use the configuration-file browser or copy it to
the card root and open it in Files. Do not copy a Windows EXE to the card.
The source profile is in `docs/profiles/Accessible-Polish.cfg`.

The import-only `accessibility touch enabled: on` setting updates the existing
private accessibility preference. It is not exported into the main saved
`config.cfg`, so later menu changes are not overwritten at every restart.
Invalid on/off values and private-setting save failures make the import fail.
As with the existing CFG loader, this is not a transaction over every setting
in the file. Settings for unavailable capabilities are ignored by those ports.

Old packages keep their original defaults. Their manifests have no
`default_profile` field. New package manifests declare `standard-en`; validators
distinguish these profiles instead of treating old Polish packages as changed.
