# Interface color presets

## Brightness and backlight duration

Settings → General Settings → Display → LCD Settings keeps these separate.
Brightness changes the light level (R1 range1–100), while Backlight and
Backlight on charging choose durations or Never/Always. They are not aliases
for one setting. Positive time choices speak their numeric duration and unit;
the old callback defect that replaced them with “Rockbox” is corrected without
renaming durations as brightness. Screen curtain is independent of both.

## Preset selection

On a color-screen player, open Settings → Theme settings → Colors → Interface color presets. The choices are actions, not a separate saved mode:

- **Dark core interface:** near-white text on a near-black background, with white selected text on a dark-blue selection bar.
- **Light core interface:** near-black text on white, with the same dark-blue selection bar and white selected text.
- **Default core colors:** restore the compiled defaults for the foreground, background, selection, separator and selection-bar style. This is not a factory reset or a complete theme restore.

Each action uses the existing saved Rockbox color settings. It immediately reapplies the interface and schedules the normal settings save; the result survives an ordinary shutdown and restart. No additional profile or configuration format is introduced. You can still adjust individual colors afterward. Another theme may replace them when loaded.

## What changes

The action selects the built-in main-screen statusbar and plain main UI, clears the main-screen backdrop and explicit UI-viewport configuration, and disables per-filetype color overrides. This prevents a previously loaded skin or background image from hiding the selected palette. Statusbar visibility and top/bottom position stay as configured.

Fonts, icon sets, playback/radio skins, remote-screen settings and accessibility settings remain unchanged. The actions do not delete or overwrite theme files. They do not automatically remember arbitrary old colors or skin selections: to return to a previous theme, reload that theme from Theme settings → Browse theme files, or restore your saved configuration. Default core colors retains the plain UI; it does not reload the previous theme or restore the default backdrop.

## Scope and energy

This is a core-interface palette, not a recoloring filter for every screen. Custom playback skins, album artwork, bitmap icons, plugins and screens that choose their own colors may look different. A file browser's custom color callback or another module can also override ordinary list text colors. New third-party themes can override the preset.

Dark appearance is independent of the screen curtain. It does not hide the interface, turn off the backlight, change brightness or promise battery savings on the R1 LCD. It introduces no background worker, recurring timer or continuous color conversion. Menu labels are localized and use ordinary Rockbox self-voicing; this does not establish Windows NVDA accessibility or physical-device acceptance.
