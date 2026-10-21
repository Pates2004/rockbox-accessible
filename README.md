# Rockbox Accessible / Talkbox

[Polski](docs/BUILD-ACCESSIBLE-PL.md) · [Build instructions](docs/BUILD-ACCESSIBLE.md)

For the player rather than SDL, use the detailed English
[native HiBy R1 build guide](docs/BUILD-ACCESSIBLE-NATIVE.md). It distinguishes
application compilation from release packaging and includes offline preparation
of the required SDK license/provenance inputs.

An experimental Rockbox development fork with in-process speech and accessibility
work. It is not an official Rockbox release. Talkbox is the accessibility layer;
the speech engine is the supplied **eSpeak 1.44.05 r34 fork**, not eSpeak NG,
system speech, a cloud service or generated voice clips.

## Scope

- Shared spoken lists, file names, settings, errors and several plugins;
  prerecorded voice-file preferences do not disable Talkbox.
- Configurable speech, Sonic-assisted high rates, music ducking, text navigation
  and text bookmarks integrated with existing audio-bookmark lists.
- Optional touch exploration/gestures, accessible typing, screen curtain,
  physical-button mappings and grouped accessibility toggles.
- HiBy R1-specific audio, power, connectivity and experimental Bluetooth work.

The shared core is intended for reuse, but **not every Rockbox target is enabled
or validated**. Integrated builds currently recognize Sansa Clip+, Clip Zip,
HiBy R1 and their SDL simulators. Other players need an appropriate platform
adapter, memory review, target build and testing; selecting an arbitrary model
does not establish a working port. Raw custom plugin screens are not universally
accessible. See [target boundaries](docs/ESPEAK-TARGETS.md) and
[plugin coverage](docs/ESPEAK-PLUGINS.md).

## Development status

This branch contains work in progress, not a new accepted binary release.
Bluetooth monitor framing, connection-intent races, reconnect integration and
full native/Windows regression gates are being reviewed. A successful build or
mock test is not physical Bluetooth, RF power, battery-life, touchscreen or NVDA
acceptance. Wi-Fi streaming/NAS, podcast services and accessible GBA/Lua support
are not implemented by this fork.

The current test-build defaults remain Polish with speech enabled. Publishing
source does not change those defaults to the planned future public-release
profile. Do not install a Windows EXE on a player. Do not flash firmware from
another HiBy model or assume a newly compiled application replaces a bootloader.

## Build and contribute

Use the [English](docs/BUILD-ACCESSIBLE.md) or
[Polish](docs/BUILD-ACCESSIBLE-PL.md) instructions, including exact eSpeak data
preparation. The detailed [contributor guide](docs/CONTRIBUTING-ACCESSIBLE.md)
explains development, validation, issue reports and pull requests in English.
Sources, tests and public documentation are included; local builds,
settings, diagnostic captures, firmware installers and private project notes
are intentionally excluded. There is no automatic hardware installer here.

A reviewed subset of Polish-only corrections (47 existing message IDs) is
maintained separately on the `polish-translation-fixes` branch so it can be
reviewed independently of TTS. Later feature-specific labels remain with their
corresponding development changes.
Official Rockbox submission remains a separate Gerrit process; publishing this
fork does not imply upstream acceptance.

Preserve the component license notices. Rockbox files generally specify
GPL-2.0-or-later; eSpeak specifies GPL-3.0-or-later. Integrated eSpeak binaries
must respect the GPLv3 requirements and all bundled component notices, including
corresponding source. See [Rockbox license](docs/COPYING),
[eSpeak license](lib/espeak/License.txt), and
[engine provenance and integration](lib/espeak/README.md). Other components retain
their own licenses; this repository does not relicense them.

Newly authored Talkbox, accessibility, Bluetooth-policy/platform integration,
build-helper and regression-test contributions are provided under
GPL-2.0-or-later. This grant does not replace the licenses of imported code,
manuals, data or firmware. In particular, inherited Marvell firmware blobs retain
their separate binary-redistribution license, not a GPL source-code grant.
