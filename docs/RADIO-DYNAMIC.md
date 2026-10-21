# Radio speech and station information

Automatic preset scanning continues while its speech is paused. A normal
navigation key stops the current announcement; the next separate key press
resumes announcements of future or the latest found frequency. Keys mapped
on release take effect on release when resuming. Holding a key does not toggle
speech repeatedly. This does not resume an interrupted utterance at its old
position and does not save a queue of all frequencies.

OK/Enter silences scan announcements until that scan ends. The normal Cancel,
Back and Power mappings retain their control meaning, including cancellation
on targets where a direction key maps to Cancel. USB, shutdown, reboot and
storage events retain their system handling. A scan interrupted by cancellation
or a system exit is not announced as completed.

On normal completion, including reaching the preset capacity, Rockbox says
"Scan complete" if interface speech is enabled. Completion is independent of
the dynamic-announcements preference and of the temporary scan mute. The next
scan starts with its own fresh speech state, and ordinary interface speech
remains available.

The Talkbox dynamic-announcements preference controls automatic found-frequency
speech when synthesis is enabled. Prerecorded voice-file behavior retains its
own menu-speech preference when synthesis is disabled. Scan display updates are
silent: they cannot create duplicate synthesized announcements. Synthesis keeps
only the latest pending frequency while speech is busy; voice-file announcements
are separated by at least five seconds. Input is checked between tuner operations,
so interruption latency also depends on the tuner driver.

On targets configured with RDS support, the radio menu provides **RDS
information**. Its two selectable, spoken rows contain the station name and
radio text, or **No RDS data** when a field is unavailable. OK refreshes both
fields and reads the selected row. Automatic metadata changes do not interrupt
this explicitly opened information screen. Reading the rows and refreshing
them work with dynamic announcements disabled. Back returns to the radio menu;
USB and power use the ordinary list and system event handling.

Station names and radio text use fixed buffers sized for the decoder's UTF-8
output: 25 and 193 bytes respectively. They are read through the common tuner
API, without changing tuner drivers or introducing a target-specific speech
engine.

## Target capabilities and validation

Both Sansa Clip+ and Clip Zip configurations define `HAVE_RDS_CAP`. Clip+
configures polling and supports selection between SI4700-family and RDA5802
tuners; Clip Zip configures an SI4700-family tuner and interrupt-driven RDS.
The SI4700 driver enables decoding according to the chip's capability bit.
The existing RDA5802 driver does not supply decoded RDS. A configuration macro
does not guarantee reception on a particular unit, station or antenna.

Isolated regression tests extract the actual radio functions and shared speech
policy and exercise them with mocked tuner, input and speech boundaries:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools/tests -p test_radio_dynamic.py -v
```

They cover synthesis, voice files, RDS and non-RDS configurations, normal scan
completion, pause/resume, Enter mute, repeat/release filtering, safety events,
bounded state, empty scans, capacity, missing metadata and explicit refresh.
Both languages use the actual catalog labels, with display/voice parity checks
and negative cases that deliberately restore the speech and safety regressions.
Generated fixtures and reports belong in central `Workspace/rockbox/radio-dynamic-tests`.
These tests do not establish audible speech, firmware build compatibility or
physical reception. The HiBy R1 software phase has no physical FM acceptance;
Clip+/Clip Zip RF/RDS, real buttons, screen readers and audio still require
separate target builds and hardware tests. Existing release artifacts are
unchanged by this source work.
