# Native eSpeak runtime adapter

## Hosted HiBy reuse

HiBy R1's `hibyos` build reuses this adapter with the same explicit bounded
pool, Unicode tables and Rockbox file API. Absolute `/.rockbox` paths therefore
follow the hosted filesystem's card-root translation, not libc's process root.
No installed UTF-8 locale or libstdc++ is required. The existing 15 MiB core
arena is separate from the engine pool; neither is a measured RSS budget.

Hosted IRQ helpers are no-ops, so the four engine guard/readiness operations
use GCC acquire/release atomics on hosted builds. The original single-core IRQ
implementation remains unchanged on bare-metal targets. The rest of the
adapter still has one initialization/synthesis owner, not a generally
thread-safe heap. Host thread/UBSan tests and a MIPS cross-build do not prove
device audio, input, RAM or battery behavior.

This is a C adapter for the supplied eSpeak engine on native, single-core
Rockbox. It is not an alternative engine or a hosted libc. The firmware owns
audio, scheduling, initialization and the TTS worker. No C++ runtime, Linux
services, mutable locale, environment configuration or writable data files
are required by this adapter.

## Build boundary

- Compile the engine and bridge with `-DRB_ESPEAK_NATIVE=1` and
  `-Ilib/espeak/native/include` before ordinary headers. GCC/newlib base
  headers are still needed. ARM GCC 13 uses `-nostdinc++` to avoid its C++
  wrapper versions of C headers; the engine does not need standard C++ headers.
- Compile **both** `native_runtime.c` and `native_text.c` as C with ordinary
  Rockbox core flags and includes, **without** the shadow header directory.
  The source files deliberately reject the replacement `stdlib.h` to prevent
  recursive calls back into their own wrappers.
- Link the existing `libtlsf` and `libutf8proc`, normal Rockbox libc, libm for
  the engine, and GCC's arithmetic helpers. Do not link libstdc++ or newlib
  libc wholesale. Native static-library ordering may need a linker group.
- TLSF must retain its native `TLSF_STATISTIC=1` and core
  `-fno-strict-overflow` flags. Its generic bit-scan implementation depends on
  wrapping signed arithmetic. A default-host-flags UBSan run detects this
  pre-existing assumption; the tests reproduce the actual core flags rather
  than disabling instrumentation.

All exported adapter declarations are in `native_runtime.h`, with C linkage
under C++. Shadow headers contain only engine-local aliases. `FILE`, `DIR`,
`struct stat`, `struct dirent` and conversion state refer to adapter types,
never to newlib's FILE layout or Rockbox's native directory layout. The empty
shadow `locale.h` intentionally offers no mutable locale APIs.

## Ownership and memory

The heap is a static, 16-byte-aligned, nonmoving 1536 KiB buffer. Override
`RB_ESPEAK_HEAP_BYTES` in the adapter build to use 1280 KiB. Its storage must
remain in normal firmware BSS, not temporary initialization memory, IRAM or
a movable buflib allocation. TLSF metadata and FILE/DIR wrappers use this
same budget. All allocation calls use explicit-pool `malloc_ex`, `free_ex`
and `realloc_ex`. The core's weak `get_new_area` must remain non-growing;
native Clip+ has no core override. TLSF initialization updates its internal
default-pool pointer, so unrelated clients in the same binary must also use
explicit pools. Separately linked plugins/codecs have their own TLSF state.

- `rb_espeak_malloc/calloc/realloc/free` reject oversized/overflowing requests
  with NULL and ENOMEM. Failed realloc preserves the old block and contents;
  realloc of a non-NULL block to zero frees it and returns NULL. Zero-length
  malloc/calloc may return an ordinary minimal allocation.
- `rb_espeak_heap_capacity/used/available/peak/failures()` expose diagnostics.
  Used/peak include allocator overhead. Available is total free space, not a
  promise of the largest contiguous allocation. Failure count is monotonic
  for the firmware lifetime. Snapshot it around a synthesis call if the
  bridge needs to detect an engine allocation failure that upstream ignores.
- Heap, I/O, conversion state, strtok and diagnostics have **one owner**: the
  initialization/TTS worker. They are not interrupt-safe or independently
  locked. Query heap statistics only while that owner is idle or from it.
  There is deliberately no reset operation invalidating retained engine
  pointers. All engine-side NULL handling remains the bridge/engine's job.

`rb_espeak_engine_acquire()` returns 1 on acquisition, 0 if already busy.
`rb_espeak_engine_release()` clears the busy flag.
`rb_espeak_engine_ready()` returns 0/1, and
`rb_espeak_engine_mark_ready()` publishes process-lifetime readiness. These
four transitions save/restore the exact prior IRQ state, using the core's
compiler barriers. They implement the native **single-core** baseline, not
a multicore lock or a replacement for all heap ownership rules.

`rb_espeak_native_yield()` calls core `yield()` unless the owner has installed
`rb_espeak_native_set_yield(callback, context)`. Passing NULL restores the
default. Set the callback while idle; callbacks must not recursively enter
the engine. File buffer fills yield too. CPU-heavy synthesis/translation
loops still need explicit yield calls from the engine integration; a PCM
callback alone does not bound time spent preparing the first samples.

## I/O and errors

`fopen` accepts only `r` and `rb`, with identical raw-byte semantics. Each
stream has a 512-byte buffer. Absolute/relative seeks inside that buffer,
including its end, only change the logical cursor; they clear EOF and undo
ungetc without clearing an existing error. External seeks validate range,
perform the Rockbox lseek first, and leave the buffered position unchanged
on failure. This matters for dictionary validation: entry-sized forward
skips must not cause a new device read for every entry.

Reads preserve partial-item fread counts, EOF versus read failure, ftell,
single-byte pushback after a consumed byte, and CR/LF bytes. All error/close
paths release wrapper memory, including failed allocations after opening a
native handle. Directory results are copied into a bounded adapter dirent.
`stat/lstat` inspect native directories or open regular files and call
`ffilesize`; on the native FAT filesystem there are no symlinks to follow.
`access` supports existence and read checks; write checks fail with EROFS.

There is no writable FILE implementation. `fwrite`, `fputc`, `fputs`,
`remove` and write-mode fopen report failure rather than pretending to save
anything. `fprintf/printf` to the two diagnostic streams store the last
message in a fixed 256-byte RAM buffer, available through
`rb_espeak_native_diagnostic()`. Truncation is reported as EOVERFLOW. They
use Rockbox's formatter, not a hosted stdout or log file. Arbitrary fprintf
to input files fails. Flushing these already-stored diagnostics succeeds;
flushing an input stream is unsupported.

`rb_espeak_errno` belongs to the single owner. File wrappers copy the core
error before cleanup; numeric wrappers bridge core strtol/strtoul errors.
Rockbox's missing EILSEQ is supplied locally with newlib's ARM value 138;
host tests retain their host's EILSEQ value. `getenv` returns NULL without
accessing the environment. sleep/usleep/nanosleep explicitly report ENOSYS
(sleep returns its unslept argument); they are not scheduling fallbacks.

## Text and numbers

Narrow ctype is ASCII-only and handles negative/non-ASCII inputs safely.
Wide classification and one-codepoint case mapping use the existing
utf8proc Unicode tables, including supplementary-plane letters. Invalid
scalars and WEOF are not classified as letters; case mapping preserves them.
Wide alpha includes letter/letter-number categories, digit uses Nd, space
uses Unicode separators plus TAB..CR and NEL, and punctuation includes
punctuation/symbol categories. This is an explicit fixed Unicode policy,
not a claim to reproduce every host locale's classification of marks.

Wide strings and UTF-8 conversion support supplementary scalars, partial
conversion state, size queries and output bounds. Invalid/overlong UTF-8,
surrogates and out-of-range scalars fail with EILSEQ. No user codepage or
locale is consulted. strtod/wcstod accept ASCII decimal/hex numbers with
exponents and inf/nan, with a dot as decimal separator and bounded exponent
processing. Their small arithmetic parser is adequate for engine numeric
parameters; it is not a correctly-rounded general replacement for a full
libc decimal-to-binary implementation. abs(INT_MIN) returns INT_MAX and
reports ERANGE instead of invoking signed-overflow undefined behavior.

## Integration responsibilities

The bridge must use these native flag functions instead of std::atomic,
check absolute bounded parent paths rather than realpath, and use fixed
Unicode checks instead of locale_t/newlocale. Keep initialization and
synthesis serialized, and handle engine allocation failures. Keep mutable
`LoadConfig()` loading and asynchronous/host playback disabled. The supplied
integration already rejects initialization modes other than synchronous.

Dictionary compilation is not a firmware runtime feature. Prefer excluding
`compiledict.cpp` and explicitly rejecting `espeak_CompileDictionary` in the
main-owned integration. Until then all write attempts fail; the adapter
does not claim that compilation or filesystem tracing works. Voice,
dictionary and phoneme data remain read-only firmware assets.

## Focused validation

From WSL/POSIX with GCC/G++:

```sh
python3 tools/tests/test_espeak_native_runtime.py
```

The test builds real adapter/TLSF/utf8proc code against narrow mocked
Rockbox headers. Normal, ASan and UBSan runs cover coalescing, realloc
in-place/movement/failure, overflow, exhaustion, 16,000 deterministic mixed
allocations, buffered seeks with actual read/seek counts, EOF, short reads,
injected I/O failures, handle cleanup on OOM, Unicode/UTF-8, fixed numeric
syntax, and IRQ/yield behavior. C++ header checks run on the host and ARMv5
when arm-none-eabi-g++ is installed; accidental core use must fail.

`build_runtime(build, flags=(), compiler="gcc")` in the test module returns
the adapter, text, TLSF, utf8proc and mock object paths for an independent
full-engine harness. Its generated mock headers are in `build/mocks`.
These sources/objects and per-check logs remain in ignored Workspace as
intentional reproducible diagnostic artifacts. They are not releases or
additional installed firmware copies. ASan sees the fixed arena as one
object; the allocator stress/content checks complement it but cannot prove
absence of every within-arena overwrite. Physical Clip+ timing, stack usage,
playback, battery behavior and screen-reader behavior are not established
by these focused host tests.
