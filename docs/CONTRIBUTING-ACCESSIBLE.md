# Contributing to Rockbox Accessible

This public fork is experimental. Its `accessible` branch contains Talkbox and
device integration work; it is not an official Rockbox release or a promise
that every player is supported. Please read the [overview](../README.md),
[build guide](BUILD-ACCESSIBLE.md), [target boundaries](ESPEAK-TARGETS.md) and the
guide for the actual target before changing or installing anything.

## Obtain and identify the source

```sh
git clone --config core.autocrlf=false --branch accessible https://github.com/Pates2004/rockbox-accessible.git rockbox
cd rockbox
git rev-parse HEAD
python3 -B tools/prepare_espeak_source.py
```

The dependency helper fetches a pinned public source revision and validates the
exact supplied speech data. Do not substitute another engine, silently rebuild
the dictionaries, edit provenance hashes to accept different inputs, or copy
libraries from an unrelated device. Existing dependency directories are not
overwritten. Keep your own work on a separate branch and retain local data
before replacing a simulator or a card installation.

Use Linux/WSL for the documented build commands. The clone option changes only
the new repository's local line-ending policy; it does not change global Git
configuration. Preserve local edits before correcting an older CRLF checkout.

## Keep changes reviewable

- Prefer a focused change with a clear description, reproduction and regression
  test. Keep shared behavior in the portable accessibility/TTS layer; use target
  guards and platform adapters for device-specific capabilities.
- Preserve existing component authors and licenses. Identify changes to imported
  files and their dates, and keep source/provenance notices consistent. Do not
  claim ownership of imported code or treat a README as relicensing it.
- Update English and Polish strings together, including spoken labels, state
  messages and errors. Do not translate identifiers or source-code APIs.
- A setting must affect actual behavior, not just store a value. Exercise both
  states, cancellation, failures and existing defaults. Keep menus in their
  established category rather than duplicating the same control elsewhere.
- Shared settings or plugin-visible structure changes need a reviewed integrated
  plugin ABI change and rebuilt bundled modules. Stock or earlier integrated
  plugins must not be mixed into a new package.

The separate `polish-translation-fixes` branch contains a reviewed subset of
corrections to existing Polish messages, without Talkbox code. Keep unrelated
translation improvements separate from feature-specific strings when practical.
The [upstream-submission guide](POLISH-UPSTREAM.md) explains the independent
Rockbox Gerrit workflow; a pull request here is not an upstream submission.

## Validate and describe the limits

Start with the focused tests described in the build guide and the relevant
component document. Include the exact commands, operating system, compiler,
target and result. Check both interface languages and keyboard navigation.
When UI behavior changes, test the complete simulator runtime, not an EXE
copied without its matching codecs, plugins and speech data.

A successful compilation does not establish device compatibility. Separate
host/unit tests, sanitizer tests, Windows simulator interaction, target-runtime
checks and physical-device results. Do not count a skipped test, a mocked radio
or an emulator as physical acceptance. Preserve failing logs; an infrastructure
error is not a passing product test. Report unavailable checks explicitly.

In particular, the Windows simulator intentionally does not operate the host's
Bluetooth radio. HiBy R1 Bluetooth requires actual headset pairing, mixed
music/speech routing, disconnection, cancellation, reconnection and shutdown
tests. See the [Bluetooth contract and limitations](ESPEAK-BLUETOOTH.md).

## Report a problem

Open an issue in this fork with:

1. The player model, hardware revision if known, firmware version and exact
   Rockbox Accessible Git revision or package name.
2. Whether this is a physical player, Windows simulator or Linux simulator.
3. Steps from a known state, the expected result and the actual result, including
   speech, focus, input mode and audio output when relevant.
4. A panic message/address or the relevant bounded log excerpt. Say if the
   problem also occurs with clean defaults; do not discard your normal profile
   merely to report an issue.
5. Tests already tried and any data-loss, filesystem or recovery concerns.

Never upload passwords, tokens, private configuration, copyrighted books/music,
personal audio captures, complete card images or proprietary firmware/library
payloads. A redacted minimal reproduction is preferable. Do not flash another
model's firmware, format a card, or weaken USB/filesystem safety to reproduce a
bug. Firmware installation and recovery are separate from application updates.

## Submit a change

Create a topic branch in your fork and open a pull request against `accessible`
in `Pates2004/rockbox-accessible`. Explain the cause, the actual fix, tests and
remaining limitations. Include documentation and matching source for any newly
distributed binary components as required by their licenses. Generated builds,
user profiles and private diagnostic artifacts do not belong in source commits.
