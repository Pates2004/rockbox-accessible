# Sonic

This directory vendors `sonic.c` and `sonic.h` from
<https://github.com/waywardgeek/sonic> at commit
`fbf75c3d6d846bad3bb3d456cbc5d07d9fd8c104`. Sonic is licensed under the
Apache License 2.0; see `LICENSE`.

## Local modification notice, 2026-10-21

Rockbox Accessible modifies `sonic.c` to preserve owned input/output buffers
and capacities when reallocation fails. Its dated source notice identifies
that local modification; the original Bill Cox attribution and Apache 2.0
license remain intact. `../LOCAL-PATCHES.json` records the original and
integrated source hashes. The supplied source and its original hash manifest
are unchanged; the integrated C source retains CRLF line endings.
