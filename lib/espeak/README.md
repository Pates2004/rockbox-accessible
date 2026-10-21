# Integrated eSpeak backend

## Provenance and license

`engine/` is an intentional integration copy of the required subset from
`D:/Rockbox/espeak-1.44.05-source/src`, repository
`https://github.com/Pates2004/espeak-1.44.05-x64`, commit
`a14831fd3af6b3df77ef23b854cd05ee05b12851` (r34). The engine's version string
is `1.44.05-r34 Windows x64`, retained verbatim on every target. This is not
distro eSpeak or eSpeak NG.
The original checkout is not modified. `UPSTREAM.sha256` records hashes of
the original files before newline normalization and integration changes.
The imported engine retains upstream mixed indentation and trailing whitespace;
its license retains original whitespace too. Sonic
retains its pinned CRLF bytes, and the exact acquisition patch keeps its final
blank line. Narrow Git whitespace attributes preserve these imports instead of
reformatting them. They do not exempt the bridge, native adapter or other project
sources from whitespace checks, nor alter the provenance hashes.
The retained upstream source headers specify GPL-3.0-or-later; the supplied
GPL v3 license text is preserved in `License.txt`.

### Integrated modification notice, 2026-10-21

Rockbox Accessible modifies the supplied r34 engine for its filesystem roots,
bounded runtime, synchronous synthesis, Unicode policy, validation, allocation
failure handling, tracked positions and defined waveform arithmetic. Dated
change notices identify the substantively modified imported files:

- `speak_lib.cpp`, `compiledict.cpp`, `dictionary.cpp`, `intonation.cpp`;
- `readclause.cpp`, `synthdata.cpp`, `translate.cpp`, `tr_languages.cpp`;
- `voices.cpp`, `wavegen.cpp`, `klatt.cpp`, `speech.h`.

The other 18 imported engine files are unchanged apart from any original
line-ending normalization and do not receive modification notices. The notices
were added on 2026-10-21 to identify this integrated version; they do not date
every preceding functional edit. Original copyright, license and warranty
notices remain intact, and the imported engine remains GPL-3.0-or-later.

The separately licensed Sonic allocation correction has its own dated source
notice and [modification record](sonic/README.md). Adding these notices changes
no engine or Sonic behavior. `LOCAL-PATCHES.json` records the updated integrated
hashes for its three existing corrections; `UPSTREAM.sha256` and `SONIC.sha256`
continue to identify the original unmodified inputs. The exact supplied
dictionary/runtime data and acquisition patch are not changed by these notices.

The r34 rebase retains Rockbox's explicit filesystem roots, bounded native
runtime, worker-local Unicode policy, binary validation, synchronous-only
output, allocation error handling, tracked-position correction and defined
waveform overflow arithmetic. Its queue/translator/data cleanup supersedes
the equivalent older local fixes, without double-freeing allocations. Dynamic
voice catalogs use explicitly cleared, zero-initialized global pointer storage;
only temporary candidate lists use scoped destructors. This avoids introducing
global C++ initialization or process-exit handlers on native Rockbox targets.

Runtime data must come from the supplied r34 **working tree**, including the
user's uncommitted dictionary replacement on 2026-10-19. The Git revision and engine
sources have not changed. `DATA.sha256` records the exact bytes of all 283
runtime files and 88 corresponding `dictsource` files; `DATA-PROVENANCE.json`
identifies the baseline delivery and the two changed files:

- `espeak-data/pl_dict`: 38,352 -> 38,350 bytes, SHA-256
  `0856492b1a316c26eda88c28f0732ce7a0314c96b17b5741867114f295b7670c` ->
  `4ba408bc999a1a63e68ce610dbecd956fd989467c2202e58f4a6dae03def5217`.
- `dictsource/pl_list`: 46,363 -> 46,346 bytes, SHA-256
  `d74869cedd46121226fd1ee92d13d02476edf577aec6dfc303a59b824a0d23b2` ->
  `c401e56f6467d9fb51b253b333a6da5ff3de4c9425a6cef43e4eb7915d594180`.

The baseline is R1 alpha11. The supplied `_−` dictionary exception, spelled
`_-` in the source, now says minus. `dictsource/pl_rules` remains byte-identical:
13,464 bytes, SHA-256 `98912b94bd1c6787502a3e5f88cf0c6a9e4252339de1615491e92cee8872eb2a`.
All other runtime and dictionary-source files match that delivery.
The phoneme binary format remains `0x014404`; no engine version, bridge API or
plugin ABI change is required for this data update.

Before freezing/packaging, call `data_provenance.validate_supplied_data(source)`
or run `python3 -B lib/espeak/data_provenance.py /path/to/supplied-checkout`.
This checks the base commit, original engine hashes, the complete data/source
inventory and every working-tree file hash. Retain its manifest/sidecar hashes
in build evidence, pack runtime bytes from `espeak-data/` and matching sources
from `dictsource/`. The original checkout remains the source of these files;
there is no duplicate vendored data tree. Do not import unrelated supplied
README, workflow or Windows build-script edits into the integrated engine.

The R1 native and simulator builders run this validation before building or
packaging and repeat it at their unchanged-input/publication gates. New R1
manifests carry `espeak_data_provenance`; runtime hashes are checked against it,
and native corresponding-source validation also binds all dictionary sources
and both provenance files. Sansa simulator builds retain their existing data
policy. Read-only verification of archived R1 releases remains independent of
the supplied checkout; manifests without the new field remain supported.

Po polsku: dane pochodzą z bieżących plików dostarczonego r34, także ze zmian
niezatwierdzonych w Git. Względem poprzedniej paczki zmieniły się tylko
`pl_list` i `pl_dict`; `pl_rules` pozostał identyczny względem alpha11.
Zmiana nazwy znaku `_-` na minus pochodzi z dostarczonego słownika. `DATA.sha256` obejmuje
283 pliki danych oraz 88 plików źródeł słowników. Kontrola
`validate_supplied_data(source)` sprawdza ich rzeczywiste bajty, kompletność,
wersję bazową i niezmienione źródła silnika. Do programu trafia `espeak-data`,
a do odpowiadającej mu paczki źródeł także `dictsource`. Zachowano oryginalny
katalog wejściowy; nie powstała dodatkowa kopia całego drzewa danych.
Buildery R1 wykonują te kontrole automatycznie przed pracą i przy publikacji.
Nowe manifesty zawierają `espeak_data_provenance`, powiązane z danymi oraz
źródłami słowników. Weryfikacja archiwalnych wydań pozostaje dostępna bez
dostarczonego checkoutu; kontrola R1 nie wymusza nowych danych dla Sans.

The ordinary PCM regression corpus contains 14,678,750 bytes. The 2026-10-15
data replacement preserves its supplied r34 reference, SHA-256
`1a2ade4051947d592063dad58586bd6cfe9fddf5b152e9b30d13984d95fd22bc`
on the Linux test host and
`405c9cc6ef2173475c6f37303e4a5b25e293c405ff440d9734743b1be8524a25`
on native Windows. The older 14,649,342-byte results later in this document
are historical r29 evidence, not current acceptance values. Holding the
engine executable constant and switching only `pl_dict` back to r29 recovers
the historical corpus exactly; the new length/hash reflect the supplied
Polish pronunciation changes in the earlier r29 -> r34 update. High-rate Sonic
chunk references are unchanged.

`tests/test_polish_data.c` supplies an additional focused corpus of 48 PL/EN
utterances at 175, 451 and 1350 WPM. `tests/run_data_tests.py` compares one
executable with the previous r34 runtime and the current supplied data, then
repeats the current run. Each utterance starts a fresh process so a changed
earlier utterance cannot advance the engine's noise/phase state and contaminate
later PCM comparisons. Expected changes must affect both actual phonemes and
PCM; control words and English must retain both. Native bounded-adapter
comparison covers PCM; that adapter deliberately does not support file output
for phoneme traces. This test streams synthesis into callbacks without opening
an audio device, changing foreground focus or injecting input.

Po polsku: dodatkowy korpus sprawdza 48 wypowiedzi PL/EN przy trzech prędkościach
(144 przypadki). Porównuje wymowę i PCM starego oraz nowego słownika tym samym
programem, uruchamiając każdy przypadek w osobnym procesie. Kontroluje rzeczywiste
zmiany `singer`/`singing` oraz `ziścić`/`ziszczać`, zachowanie rodzin
`singiel`/`Singapur`, innych słów kontrolnych i angielskiego oraz powtarzalność.
Test adaptera z ograniczoną pamięcią porównuje PCM. Testy nie odtwarzają dźwięku
ani nie przejmują klawiatury lub fokusu.

`tests/test_dictionary_source.cpp` redirects compiler output into a private
diagnostic directory after loading the supplied phoneme tables and Polish
voice. It reads the original `dictsource` files without copying or editing
them. The native Windows test reproduces the supplied 38,352-byte `pl_dict`
exactly (3152 entries, 706 rules, 120 groups). A Linux `C.UTF-8` rebuild has
33 different Georgian character entries because of Unicode case mapping;
its 6375 compiled rule bytes are identical. This is a documented compiler-host
difference, not a reason to replace the supplied runtime dictionary. Packaging
must preserve its exact bytes, rather than regenerate it on Linux.

Po polsku: test odtworzenia źródeł zapisuje wynik wyłącznie w prywatnym katalogu
diagnostycznym. Windows odtwarza dostarczony słownik bajt w bajt. Linux z lokalizacją
`C.UTF-8` inaczej przetwarza wielkość 33 znaków gruzińskich; część reguł pozostaje
identyczna. Pakowanie zachowuje oryginalny słownik użytkownika, bez zastępowania
go wynikiem kompilacji linuksowej.

## Public C interface

The newly authored Rockbox bridge, native platform adapter, TTS integration,
build helpers and their regression tests are provided under GPL-2.0-or-later.
This grant covers new contributions only, not imported engine/Sonic code or
unchanged third-party portions. Their original notices remain applicable; the
combined eSpeak firmware uses GPLv3-compatible terms. See
`docs/ESPEAK-CLIPPLUS.md` or `docs/ESPEAK-CLIPZIP.md` for runtime notices, corresponding source and the
bounded licensing-review limitations.

Include `rb_espeak.h`. One Rockbox TTS worker owns initialization and synthesis.
There are no backend threads, SDL calls, audio devices, PortAudio, MBROLA or
SAPI calls. Optional vendored Sonic processing handles extended rates in
process. The callback is the only output route.

- `rb_espeak_init(parent)` returns 22050 on success, a negative result on error.
  Pass the directory containing `espeak-data`, normally
  `<simulator-directory>/simdisk/.rockbox`, not `espeak-data` itself.
  The parent is resolved immediately, so later working-directory changes do
  not redirect data access. Missing, empty, excessive-length and invalid roots
  fail without trying HOME, environment overrides or system data directories.
- Initialization is process-lifetime. Repeating the same resolved parent is
  idempotent; switching roots after successful initialization is rejected.
  A failed initialization may be retried. There is intentionally no public
  terminate/reload operation that could invalidate menu pointers.
- `rb_espeak_synth` is synchronous and requires NUL-terminated UTF-8 text.
  Language IDs include `pl`, `en`, `en-us`; variant IDs are exact,
  case-sensitive filename suffixes such as `m3`, `Alex`. NULL or empty variant
  means the base voice. Text and user context must survive until return.
- The callback receives signed PCM16 little-endian mono, at the sample rate
  returned by init, in blocks of at most 441 samples (20 ms). Samples are valid
  only during the callback. Copy/consume them before returning. There is no
  zero-length or terminal callback in this bridge; function return is completion.
  Callback zero continues, nonzero aborts. The bridge returns `RB_ESPEAK_OK`
  (0), `RB_ESPEAK_ABORTED` (1), or a negative error code.
- Queue/backpressure, cancellation flags, dropping already queued audio and
  playback through the Rockbox mixer belong to the caller. Do not call engine
  functions from callbacks; recursive/concurrent bridge synthesis is rejected.
- Rate is clamped to 80..1350, pitch/range to 0..99, volume to 0..300, wordgap
  to 0..2340 (10 ms units at default rate). Parameters are absolute, not relative.
  Rates 80..450 bypass Sonic; higher rates use the supplied fork's native
  preparation and Sonic time compression. A build without Sonic caps actual
  synthesis at 450. Rate 0 is not a special/default rate: it clamps to 80.
- The synthesis signature is `rb_espeak_synth(text, language, variant, rate,
  pitch, volume, range, wordgap, punctuation, callback, user)`. `range` remains
  pitch modulation range; it is not a punctuation parameter. `punctuation` is
  required and accepts only 0..3 (`RB_ESPEAK_PUNCT_NONE`, `SOME`, `MOST`, `ALL`,
  each with the `RB_ESPEAK_PUNCT_` prefix). Other values, including negative
  values and integer extremes, return `RB_ESPEAK_INVALID_ARGUMENT` before
  touching the engine or invoking the callback. Existing callers must add this
  argument immediately after `wordgap`; use `RB_ESPEAK_PUNCT_NONE` to preserve
  their previous behavior.
- Choices are immutable after successful init. Names and IDs remain valid for
  the process lifetime; counts are zero before publication and invalid indexes
  return NULL. The variant list includes a first `Default` entry with empty ID.
  Enumeration scans supplied voice files directly, avoiding the legacy engine's
  150-entry combined list limit. MBROLA, the duplicate `default` language voice,
  and voices without a readable structurally valid dictionary are omitted.
- `rb_espeak_validate_voice` returns 0 for a published language/variant pair,
  negative otherwise. It only reads immutable metadata, never touches engine
  state or the filesystem, and is safe alongside synthesis after init.
- `rb_espeak_synth_tracked` adds a word-position callback: one-based Unicode
  character index and milliseconds within generated PCM. These are synthesis
  events, not a playback clock. Rockbox maps them to UTF-8 offsets and compares
  them with consumed voice PCM. Empty phantom and out-of-input word events are
  omitted. This legacy engine emits invalid sentinel positions for some generated
  punctuation names: the cursor remains at the preceding lexical word until the
  next valid event, rather than jumping beyond the submitted text.

- `rb_espeak_synth_character` uses the supplied native `tts:char` mode through
  a generated numeric entity, including on Windows where wchar_t is only 16 bits.
  It never interprets document text as SSML. Unnamed characters producing no
  nonzero PCM fall back to `Unicode` plus their decimal number; zero volume and
  cancellation do not trigger a fallback. All normal settings remain unchanged.
- On Linux SDL simulators, Unicode classification uses a worker-local `C.UTF-8` or
  `en_US.UTF-8` locale, restored after each operation. On Windows, a thread-local
  selector supplies an explicit CRT locale to wide classification/case-mapping
  calls. Neither implementation modifies the process-global locale.
- HiBy R1 reuses the bounded native runtime and utf8proc Unicode policy instead
  of requiring either libc locale. Hosted file paths go through Rockbox's
  filesystem API, and hosted engine guards use acquire/release atomics.

## Optional high-speed Sonic backend

`sonic/{sonic.c,sonic.h,LICENSE,README.md}` is an intentional retained integration
dependency copied byte-for-byte from the supplied fork's
`platforms/windows/third_party/sonic/`. It vendors upstream
<https://github.com/waywardgeek/sonic> commit
`fbf75c3d6d846bad3bb3d456cbc5d07d9fd8c104`, under Apache-2.0, separately from
the GPL-3.0-or-later engine. `SONIC.sha256` records exact supplied-file hashes,
including CRLF endings. Original notices remain intact; neither the original
checkout nor `UPSTREAM.sha256` changes. Packages must retain `sonic/LICENSE`,
`sonic/README.md` and `SONIC.sha256` as well as the existing engine license.
Local `sonic/.gitattributes` disables newline conversion for these four exact
dependency files, overriding the repository's automatic text normalization.

`espeak.make` defaults to `ESPEAK_SONIC=1`; `ESPEAK_SONIC=0` excludes the Sonic
object and preserves the old actual maximum 450 without changing the public
ABI. Use a fresh build directory when changing this option. Sonic is compiled
as C11 with `CC` (including the MinGW cross prefix); the wrapper/engine remain
C++11. `ESPEAK_CFLAGS` defaults to `ESPEAK_CXXFLAGS`, including sanitizer flags.
No separate library installation, audio backend, global setting or SAPI is
required. Existing callers select high speed solely through their canonical
WPM argument; settings/UI/relative-percent conversion belong to the parent.

The wrapper clamps signed integer extremes before arithmetic. After voice
selection it calls `espeak_SetSonicRate(target)` only for targets above 450.
Every prepared high-rate operation creates a mono 22050 Hz stream with speed
`adjusted_rate / 175.0f`. Nonpositive adjusted rates fail safely before creating
a stream. Unlike the supplied SAPI wrapper, a positive adjusted rate at or
below 450 still uses Sonic: the native hook enables prepared articulation based
on the raw requested rate, not the adjusted rate. Omitting Sonic after that
preparation caused a large slowdown for speed-modified voices such as `jbo`.
Pitch, resampling rate and Sonic volume stay at unity.
Native Sonic preparation is reset to 0 at entry/exit of an owned operation,
including setup failure, synthesis/stream error and callback abort. Invalid
arguments and rejected concurrent/reentrant calls do not touch an active
operation's state. No buffered tail is delivered after abort or error.
Successful synthesis flushes once, drains blocks of at most 441 samples and
destroys the stream. Character fallback shares that stream; muted characters
do not trigger audible fallback. All ordinary-rate PCM bypasses Sonic entirely.

Normal Sonic output callbacks always contain 441 samples (20ms output audio).
The stream retains fewer than 441 available output samples between native input
callbacks; only final flush may deliver a smaller, final callback. No extra
unbounded audio buffer is added. Word marks remain gated by the output block
that carries their retimed clock; abort still discards all buffered tail.
This matters for synchronous mixer consumers: forwarding every tiny native
input's compressed result creates almost the same number of queue handshakes
at 451 and 1350 despite three times less audio. The nine-sentence diagnostic
previously emitted 2141 callbacks at 451 and 2192 at 1350 (averaging 174 and 56 samples).
Full output blocks reduce those to 845 and 279 without changing a single PCM
byte. Runners compare complete high-rate PCM SHA-256 against the pre-chunking
Linux/native Windows fingerprints, and enforce no nonfinal partial blocks.
Whole-utterance native mixer playback duration and reader throughput must also
be validated by the parent; synthesis sample counts alone do not prove real
playback speed or absence of scheduling starvation.

**The inherited transition is not monotonic at 450/451.** High-speed native
preparation differs from the ordinary articulation curve. In the Linux test
phrase, 450 gives 38,284 samples, 451 gives 40,605, and 1350 gives 13,367. The supplied
`jbo` voice has `speed 80`: 451 adjusts to 360, 563 to 450, and 564 to 451.
All these prepared rates now receive their matching Sonic compression. The
inherited SAPI bug (uncompressed preparation throughout 451..563) is deliberately
not reproduced. Regression tests require shorter output as the rate increases
through 451, 475, 500, 525, 550 and 563, and reject a large boundary slowdown.
The smaller ordinary/prepared articulation transition remains; there is no
claim that every numerical increase shortens every utterance at that boundary.

Tracked Sonic events retain real native word/Unicode positions. Their times
are rounded up after division by the voice-adjusted speed; a fixed 256-entry
queue dispatches them only when the corresponding compressed output block
exists. Times are monotonic, bounded by actual final output (including flush)
and never forwarded as uncompressed synthesis milliseconds. Queue exhaustion
fails the operation rather than silently dropping events or growing without
bound. Phantom, duplicate/backward and out-of-input word positions are omitted.
The caller must still compare marks with **consumed** PCM, not callback arrival,
and retain its pause/generation handling. Sonic's pitch-period overlap makes
this proportional word timing approximate, not sample-exact phoneme alignment.

Standalone runners now include `test_sonic.c`: all 371 ordinary integer rates
are compared byte-for-byte with the native callback; representative extended
rates and signed extremes measure actual output/nonzero PCM. Tests capture
real pre-Sonic events and verify compressed timestamps, 2000-word streaming,
all 54 languages/all 105 variant choices, voice speed modifiers, mute, character
fallback, punctuation, both callback reentry paths, early/final-drain abort,
create/write/read/flush/native-synthesis faults, zero/negative adjusted-rate
faults, cleanup and recovery. A real
voiced sample's autocorrelation compares pitch before/after compression (15%
tolerance); this is not a human listening assessment. Repeated synthesis has
small native duration/noise variation, so same-process clamp checks tolerate
one 20 ms block; the separate fresh-process ordinary corpus must match exact
historical SHA-256 and byte count twice on each platform.

Run standalone Linux suites in a new Workspace directory, or omit --workspace
for a timestamped directory. Existing builds are never overwritten:

```sh
python3 -B lib/espeak/tests/run_tests.py /path/to/espeak-1.44.05-source
python3 -B lib/espeak/tests/run_tests.py /path/to/espeak-1.44.05-source --sanitize address
python3 -B lib/espeak/tests/run_tests.py /path/to/espeak-1.44.05-source --sanitize undefined
python3 -B lib/espeak/tests/run_tests.py /path/to/espeak-1.44.05-source --without-sonic
```

On native Windows run `python -B lib/espeak/tests/run_windows_tests.py
D:/Rockbox/espeak-1.44.05-source`, optionally with `--without-sonic`. It builds
only the standalone backend/diagnostics through WSL MinGW, then executes them
natively. It does not access or rebuild the parent simulator executable.
Results and deliberate data fixtures remain under Workspace; superseded
diagnostic binaries belong in snapshots. Sanitizers cover the Sonic C object
as well as the engine/bridge. No physical-player memory/performance, GUI,
pause/playback, NVDA or whole-simulator validation is implied by these tests.

## Punctuation levels and engine constraints

These levels control native punctuation-name announcements, without replacing
characters, injecting spoken words, enabling SSML, or modifying input text:

| Bridge level | Native `espeakPUNCTUATION` | Native punctuation list |
| --- | --- | --- |
| 0: none | `espeakPUNCT_NONE` | Empty |
| 1: some | `espeakPUNCT_SOME` | `.,;:!?` |
| 2: most | `espeakPUNCT_SOME` | `.,;:!?"'()[]{}-` |
| 3: all | `espeakPUNCT_ALL` | Empty; the native all mode ignores lists |

Thus some selects six ASCII sentence marks. Most selects those six plus double
quote, apostrophe, both parentheses, both square brackets, both braces, and
hyphen-minus: fifteen characters total. All additionally announces eligible
characters outside those lists, including underscore and vertical bar. These
are bridge definitions, not a fourth native eSpeak mode. Native enumeration
values are none=0, all=1, some=2, so passing the bridge ordinal directly to
`espeak_SetParameter` would be incorrect.

After voice selection, every valid utterance sets both the list with
`espeak_SetPunctuationList` and the mode with `espeak_SetParameter`, including
an empty wide string for none/all. NULL is not a list reset: this engine rejects
it. Both return values are checked. The engine copies at most 59 wide characters;
both supported lists fit. Synthesis remains under the existing engine guard.
Success, cancellation, a preceding different level, and previously supplied
native settings cannot choose the next utterance's punctuation policy.

The supplied 1.44.05 engine first checks `iswpunct`, then applies its list filter
in `ReadClause`, and uses language dictionary character names, translation
rules and, when enabled by that language, English fallback. None disables
explicit announcements; it does not remove punctuation, sentence pauses,
intonation, number interpretation, or symbols already pronounced by ordinary
dictionary rules. For example, slash, backslash and plus can already be spoken
at none; adding them to most would not create a useful extra level for the
tested English/Polish data. Some symbols' effects depend on the language.
Three dots become U+2026 inside the engine, not three individually selected
periods. The exact some/most lists deliberately do not include U+2026. Ellipsis
may still be pronounced by a language's ordinary rules. All means the engine's
native all behavior, not a promise to speak every Unicode symbol literally.

Enabling punctuation exposed a pre-existing stack overread even for
`test . test`: `AnnouncePunctuation` appended phoneme text and returned a clause
without advancing `charix_top`. `TranslateClause` consequently placed its
source-index sentinel before the appended text and scanned past `charix[704]`.
ASan and strict UBSan reproduced this through both the native and bridge paths.
The only engine change for this feature advances `*charix_top = ix` before
that existing early return. It preserves the upstream algorithm and supplied
data rather than rewriting the parser or hiding the issue with a larger array.

Playback-position tests exposed another inherited error: `TranslateClause`
selected a -1 multibyte continuation sentinel as the first word's character
index (reported as 2047 for an initial Polish letter). It now skips nonpositive
entries, matching subsequent-word handling. Character-mode tests also exposed
undefined signed left shift in dictionary suffix flags. Multiplication by 65536
preserves the signed value without shifting a negative operand. These are narrow
integration fixes; the supplied source checkout and dictionaries stay untouched.

The isolated native and bridge punctuation modes each exercise 28 symbol cases
at four levels in English and Polish. For all fifteen selected marks and the
all-only underscore/vertical bar, they verify phoneme-list membership and over
100 ms of additional nonzero PCM, not just a hash difference: the engine's noise
generator can vary samples even without a parameter change. They also exercise
two/three/four repeated question marks, all 16 level transitions per language,
and report language-dependent symbol behavior. Bridge tests additionally check
invalid values without callbacks, foreign native settings, reentry, cancellation
and recovery. Punctuation runs are separate from the existing `pcm` corpus so
its historical regression hashes remain comparable.

Historical punctuation-milestone validation on 2026-10-04 used these commands
(Linux commands run from the project root in WSL Ubuntu-24.04):

```sh
python3 lib/espeak/tests/run_tests.py /mnt/d/Rockbox/espeak-1.44.05-source --workspace Workspace/espeak-punctuation/final
python3 lib/espeak/tests/run_tests.py /mnt/d/Rockbox/espeak-1.44.05-source --workspace Workspace/espeak-punctuation/final --sanitize address
python3 lib/espeak/tests/run_tests.py /mnt/d/Rockbox/espeak-1.44.05-source --workspace Workspace/espeak-punctuation/final --sanitize undefined
```

```powershell
python lib/espeak/tests/run_windows_tests.py D:/Rockbox/espeak-1.44.05-source
```

All four suites pass, including existing 54-language/105-variant coverage,
the C ABI, pitch/range/wordgap, cancellation, corrupt-data cases, native and
bridge punctuation, and (on Windows) Unicode relocation and locale isolation.
Linux evidence is in `Workspace/espeak-punctuation/final/{normal,asan,ubsan}`;
Windows evidence is in
`Workspace/espeak-windows-tests/20261004T174848441598Z`, including the punctuation
suite repeated against the Unicode-path fixture. The normal/ASan/UBSan legacy
PCM streams still exactly match the prior 14,649,342-byte Linux corpus and
SHA-256 `50264c806c4679f11f528e7b2f7e9be4ce21137c9676d9162b13a7faff9b7aca`.
Two Windows captures match the prior corpus size and SHA-256
`e0dbcac29aad6440f5460ae454b144d48fc03ac2aa4de33f4fa5533886e23764`.
The checked comparison commands and source hashes are recorded in
`Workspace/espeak-punctuation/summary.json`.

Superseded diagnostic builds and pre-fix sanitizer reproducers were moved,
not copied, into
`snapshots/espeak-punctuation-before-charix-fix-20261004T1747452199906Z`, preserving
their original relative paths and all file hashes in `manifest.json`. Deliberate
corrupt-data and Windows Unicode relocation copies remain useful test fixtures,
not installed releases. Choose a fresh workspace for future builds or archive
the previous diagnostic build before replacing it. These tests neither run nor
modify the simulator GUI suite; actual reader/NVDA validation remains outside
this backend change.

## Runtime data

No data files are vendored here. Staging belongs to the top-level integration.
Required under the explicit `parent/espeak-data` are `phondata`, `phonindex`,
`phontab`, `intonations`, language dictionaries (`pl_dict`, `en_dict`, etc.),
and corresponding `voices/` files. Variants live under `voices/!v` and are
optional. Stage the supplied complete data set for all languages and variants.
The phondata version must be `0x014404`. Paths must fit the legacy 150-byte
data-directory buffer including the terminating NUL; oversized paths fail.
Windows paths at the C interface are UTF-8, not the active Windows code page.
The bridge resolves the parent with wide Windows handle APIs, enumerates voices
with wide directory APIs, and shares UTF-8-to-UTF-16 file/stat wrappers with the
engine's core-data, dictionary and voice loaders. Polish and other non-ACP folder
names and filenames are supported within the same 150-byte UTF-8 directory
limit. This is not unrestricted Windows long-path support. Directory reparse
points encountered while scanning voices are skipped, like POSIX symlinks.

Only trusted, coherent data from the supplied checkout is supported. Header,
size, dictionary hash-chain and phoneme-table checks detect common packaging
errors; they are not a complete hostile-binary-data validator. Packaging should
verify exact file hashes. In particular, the supplied Polish dictionary is
38,175 bytes, SHA-256
`10965e1c9574e9fcf591d1b537036d0ccdd25d18f14fd254a1278437537397e8`.
There is no runtime dictionary compilation and no host `config` processing:
logging and sound-icon paths from that file are intentionally not loaded.
External sound-file loading/conversion is disabled, including the old SoX
fork/exec and temporary-file path.

## Build and local changes

`tools/root.make` includes `espeak.make` when `ESPEAK=1`. It supports the hosted
`APP_TYPE=sdl-sim` branch and the native firmware branch with empty `APP_TYPE`.
Configure admits SDL simulators and experimental Clip+/Clip Zip firmware, provides
HAVE_ESPEAK and rejects other native targets until separately ported/validated.
The 16 engine translation units plus the bridge are compiled with `$(CXX)`,
C++11, `-fno-exceptions -fno-rtti`, independent host headers, and their own `.d`
dependencies. They must not enter the Rockbox `OTHER_SRC` dependency scanner,
which forcibly includes Rockbox configuration/libc headers. The archive is
appended to CORE_LIBS and host C++/math libraries to GLOBAL_LDOPTS.
When `CROSS_COMPILE` is set and `CXX` is only Make's built-in default (or unset),
the fragment selects `$(CROSS_COMPILE)g++`. An explicit `CXX` still wins. The
parent build must supply the matching `AR`, C compiler and link configuration;
this fragment does not configure or package the simulator.

Local engine changes disable MBROLA and implicit async; enforce synchronous
initialization with an explicit bounded path; leave locale handling to the
bridge; skip host configuration; align PCM buffers to complete samples; check
callback presence; validate basic data lengths and dictionary offsets; propagate
voice/dictionary failures; free failed reads, intonations and translators on
termination; release queued voice copies when synthesis is aborted; and wrap
Klatt's sampled excitation interpolation at the waveform period boundary.
The Indic consonant list is NUL-terminated to fix the ASan-reproduced overread
when selecting Hindi/Tamil translators.
The Lojban sentence-marker lookbehind now checks the start of the clause buffer.
Further UBSan-driven changes remove the unused three-byte `c123` expression
(its negative-char shift had no consumer), use an unsigned 32-bit accumulator
for byte-packing in `TransposeAlphabet`, replace three negative-capable pitch
shifts with multiplication by 256, and index Klatt's extra parameters through
the actual `klattp2` array rather than past the five-element `klattp` array.
Original phonetics, Polish ci fixes, number rules, Klatt and all supplied variant
syntax remain intact. Upstream generic CLI/compiler/trace functions are not
part of the supported public bridge even where retained to satisfy dependencies.

Linux/MinGW Windows simulators use host services. The native ARM adapter in
`native/` replaces filesystem/Unicode/locale/allocation services and uses a
bounded 1.5 MiB TLSF pool. Native initialization and synthesis use a dedicated
128 KiB worker stack. Double-precision math still has a substantial CPU cost;
real-time speed, remaining memory, stack high-water and recording/playback need
physical Clip+/Clip Zip tests. Legacy source produces GCC warnings; successful
compilation does not establish absence of defects or safety for arbitrary input.

The three reproduced numeric overflows in `wavegen.cpp` are now fixed with
explicit modulo-2^32 arithmetic, not saturation or changed waveform scaling:

| Pre-fix integration site | Cause and defined replacement |
| --- | --- |
| Phase addition, lines 1194/1278 before this patch | `wavephase` is now `uint32_t`, so both additions wrap. The old signed `> 0` test becomes `0 < phase <= INT32_MAX`; the subsequent negative test becomes `phase > INT32_MAX`. Extracting the high 16 bits produces the same phase index. |
| Left/right peak accumulation, lines 862/866 before this patch | `AddHarmonicWrapped` multiplies and adds as `uint32_t`, then maps the high-half bit patterns to signed values using `-1 - (UINT32_MAX - bits)`. Every cast is representable. The following signed right shift and amplitude scaling retain their original inputs. |

For the actual UBSan reproducers, the signed phase calculation
`2147483647 + 20948012` now explicitly represents the wrapped signed value
`-2126535637`. The harmonic sums `1869628857 + 534240000` and
`1871686578 + 398566707` preserve `-1890598439` and `-2024214011`, respectively.
There is no out-of-range unsigned-to-signed conversion, new 64-bit arithmetic
in the sample loop, or sanitizer/compiler overflow suppression. Keeping the
harmonic table signed is intentional: simply widening it or making it unsigned
would change the subsequent shift, square and PCM result.

The normal, ASan and strict UBSan suites all pass after these changes. This is
coverage of the supplied test corpus, not a proof for arbitrary text, parameters
or data. Existing compiler and text-processing GCC warnings remain inventoried
in build logs. Other legacy signed right shifts still assume arithmetic right
shift on the selected Linux compiler; ARM numeric portability is not established.
Per-request dictionary validation and voice loading are deliberately retained;
there is no unvalidated voice cache or ARM performance claim.

## Targeted validation

The current alpha3 backend validation binaries are in
`Workspace/espeak-alpha3-final/{asan,ubsan}` and the native Windows run
`Workspace/espeak-windows-tests/20261004T193150492101Z`. Both Linux sanitizer
suites and the Windows suite pass, including tracked Unicode positions,
native character reading, punctuation and the unchanged ordinary PCM corpus.
Superseded diagnostic builds have been moved into
`snapshots/diagnostic-builds-before-alpha3` or the earlier
`snapshots/diagnostic-builds-before-expanded-speech`, retaining their original
Workspace-relative paths. Their reports and PCM hashes remain in Workspace;
the relocation map is `Workspace/maintenance/prior-diagnostic-builds-alpha3-20261004.json`.
Use a fresh workspace for another build rather than overwriting prior evidence.

From Linux, without building Rockbox:

```sh
python3 -B lib/espeak/tests/run_tests.py /absolute/path/to/espeak-1.44.05-source --sanitize none
python3 -B lib/espeak/tests/run_tests.py /absolute/path/to/espeak-1.44.05-source --sanitize address
python3 -B lib/espeak/tests/run_tests.py /absolute/path/to/espeak-1.44.05-source --sanitize undefined
```

Tests compile a C caller and exercise PCM, all supplied variants and enumerated
languages, parameters, cancellation/reentry, immutable choices, global-locale
preservation, Polish ci phonemes, long input, explicit-root failures, binary
version/truncation, and the 50 ms buffer-alignment regression. Reports and
builds stay in central `D:/work/Workspace/rockbox/espeak-tests` by default.
An optional absolute `--workspace` must remain under central Workspace.
Small intentional data copies for
fault injection are retained there, not in the source tree. Subsequent runs
reuse only the known six-file fixture and reject unexpected content or symlinks.
Sanitizer and ordinary builds are separate because their executable
instrumentation differs. ASan runs with leak detection and halt-on-error;
UBSan runs with halt-on-error, without exclusions.

### Verified results (2026-10-04, Ubuntu 24.04, GCC 13.3, x86-64)

- 54 language choices and all 104 supplied variants plus the default generate
  nonzero PCM. The variant sweep uses Polish; this is not the full cross-product
  of every language and every variant, or a perceptual pronunciation assessment.
- All 11 upstream Polish `ci` phoneme regression fragments pass.
- Rate 80/450 produces 79,600/11,885 samples for `Pierwszy drugi trzeci.`;
  wordgap 0/40 produces 37,287/84,138. Volume 0 is entirely silent.
  Independent pitch and range 0/99 changes produce different PCM hashes.
- Cancellation stops after the requested second callback; the next synthesis
  succeeds. Callback reentry is rejected; immutable voice metadata is readable.
- Invalid paths/voices, data version/truncation, long text/numbers and twelve
  direct 50 ms initialization/synthesis/termination cycles pass. Undefined
  archive symbols contain no thread/audio backend or external sound converter.

For the focused wavegen changes,
`snapshots/espeak-numeric-regression-reference-20261004T153557058448Z` holds
one diagnostic executable linked before the patch, its compiler/source/archive
provenance and reference PCM hashes. It is an intentional retained regression
reference, not a release or a second source/data tree. Two fresh executions
established that the baseline stream is deterministic. `numeric-after`,
`asan/pcm-regression` and `ubsan/pcm-regression` contain post-fix hashes and
per-utterance diagnostics, not extra executables or PCM copies.

`tests/hash_pcm.py` streams actual callback PCM through SHA-256, without saving
audio files. The entire corpus before/after, including cancellation, yields
14,649,342 identical bytes by length and SHA-256:
`50264c806c4679f11f528e7b2f7e9be4ce21137c9676d9162b13a7faff9b7aca`.
Ordinary `-O2`, ASan `-O1` and UBSan `-O1` results match that baseline. To compare
a new test executable against the retained baseline:

```sh
python3 -B lib/espeak/tests/hash_pcm.py Workspace/espeak-alpha3-final/ubsan/test_backend \
  /absolute/path/to/espeak-1.44.05-source Workspace/espeak-alpha3-final/ubsan/pcm-new \
  --compare snapshots/espeak-numeric-regression-reference-20261004T153557058448Z/pcm.sha256.json
```

Historical `ubsan/recovery.log` and `ubsan/remaining-ub.log` document earlier
reproducers, not the final status. Current `normal/result.log`, `asan/result.log`
and `ubsan/result.log` record passing post-fix runs. No full Rockbox build or
physical ARM test is part of this backend validation.

## Windows backend validation

The Windows port retains this exact fork, phonetics and data format. It does
not enable SAPI, PortAudio, MBROLA, asynchronous synthesis or a new audio device.
The existing `_WIN32` engine subset compiles without SAPI SDK headers. Engine
changes for this port are limited to selecting the locale compatibility header
and using the shared file/stat wrappers on supported runtime loading paths.
Raw upstream CLI/compiler/listing functions remain outside the bridge contract.

The tested MinGW legacy MSVCRT compatibility layer cannot enable per-thread CRT
locale mode: `_configthreadlocale(_ENABLE_PER_THREAD_LOCALE)` returns `-1`.
Consequently, the bridge does not call `setlocale` or `_configthreadlocale` on
Windows. It creates an immutable `Polish_Poland.1250` `_locale_t`, selects it
using a scoped C++ `thread_local` pointer, and routes engine `isw*`/`tow*` calls
to their explicit `_l` counterparts. The locale is for Unicode classification
and case mapping, not decoding text or filenames; both remain UTF-8. Failure to
create/validate that locale fails initialization rather than changing global
state or silently using the C locale. The guard restores its prior selector on
success, early returns and cancellation. Linux retains its POSIX locale path.

To run the isolated native Windows suite from Windows PowerShell, with Python
and `x86_64-w64-mingw32-gcc/g++/ar/nm/objdump` installed in WSL Ubuntu-24.04:

```powershell
python lib/espeak/tests/run_windows_tests.py D:\Rockbox\espeak-1.44.05-source
```

The harness tests cross-compiler selection without a `CXX` override, compiles
the archive plus a C ABI caller and a targeted platform harness, and executes
the resulting `.exe` files on Windows, not Wine. Diagnostic executables link
the GCC/C++ support statically; this does not set release/simulator linkage
policy. Their inspected DLL imports are Windows `KERNEL32`, `msvcrt` and
`ADVAPI32`, with no SAPI, SDL, PortAudio, MBROLA or external MinGW runtime DLL.
The archive has no audio-backend/thread-creation imports. A simulator linked
dynamically with `-lstdc++` can still need MinGW runtime DLLs; packaging belongs
to the top-level build.

Each run uses a new timestamped directory below
`Workspace/espeak-windows-tests`, with build logs, dependency reports, source
hashes, diagnostic executables and test results. A verified full copy of only
the supplied data is retained under a Polish/Chinese path containing spaces
for relocation regression; a separate six-file copy intentionally exercises
corrupt data. These are useful test fixtures, not extra installed releases.
The platform test also retains a tiny Unicode-named file for file/stat evidence.
No existing executable is overwritten. Archive superseded diagnostic builds
in project `snapshots` before replacing them, according to project policy.

Verified with GCC 13 MinGW x86-64 and native Windows on 2026-10-04:

- All 54 language choices and 105 variant choices (104 plus default) synthesize
  nonzero PCM, both from the original ASCII root and the Unicode/space root.
- The existing Polish `ci`, parameters, reentry, cancellation/recovery, long
  input and twelve 50 ms lifecycle checks pass on Windows.
- Main-thread/global CRT locale and case mapping remain unchanged while a
  different thread synthesizes. Nested selectors restore correctly, parallel
  synthesis is rejected, and worker selectors clear after success and abort.
- Invalid UTF-8, empty/excessive/missing/wrong-level roots, corrupt binary
  version and truncated phoneme tables fail; a rejected initialization can be
  retried. Data remains accessible after changing the process working directory.
- UTF-8 folders and filenames containing Polish and Chinese characters are
  tested through the shared wide filesystem wrappers without ACP conversion.
- Linux normal, ASan and strict UBSan suites remain passing. The normal PCM
  corpus remains 14,649,342 bytes with SHA-256
  `50264c806c4679f11f528e7b2f7e9be4ce21137c9676d9162b13a7faff9b7aca`.
- Two independent Windows corpus runs produce the same 14,649,342 bytes and
  SHA-256 `e0dbcac29aad6440f5460ae454b144d48fc03ac2aa4de33f4fa5533886e23764`.
  Windows and Linux hashes differ; cross-platform PCM equality is not promised.

For Linux validation without touching older test artifacts, supply a fresh
workspace (and optionally `--sanitize address` or `--sanitize undefined`):

```sh
python3 lib/espeak/tests/run_tests.py /absolute/path/to/espeak-1.44.05-source \
  --workspace Workspace/espeak-windows-tests/linux-new
```

Auditory quality, UNC/network-share behavior, unrestricted long paths,
full simulator GUI/audio and screen-reader integration
are not established by these isolated tests. Full simulator configuration,
linking, release packaging and GUI validation remain the parent integration's
responsibility. No upstream data, `UPSTREAM.sha256`, tools or apps are changed
by this backend port.

## Local memory safety corrections, 2026-10-19

The integration now carries two local safety corrections beyond the supplied
sources: `engine/tr_languages.cpp` checks translator allocation before language
setup, and `sonic/sonic.c` retains owned input/output buffers and capacities if
reallocation fails. Sonic retains its CRLF endings. These changes do not alter
linguistic rules or supplied dictionary data, and the original checkout remains
read-only. The original supplied-file manifests `UPSTREAM.sha256` and
`SONIC.sha256` remain unchanged; `LOCAL-PATCHES.json` records both original and
exact integrated hashes. This section qualifies the earlier byte-for-byte Sonic
description: the integration source now includes these explicitly recorded local
changes. Keep the local patch manifest with the integration sources.

The native bridge reports newly observed allocator failures even when an upstream
operation returns success. Its proper ownership test exercises translator and
Sonic allocation failures, cleanup, recovery, callback reentry and cancellation.
`tests/run_native_tests.py` runs it under the requested sanitizer without building
the complete application, and reuses its single hosted reference library for
Sonic tests, nine actual Polish minus phoneme/PCM cases, and source compilation
of the supplied Polish dictionary into private output for byte comparison.

Run the dependency and provenance checks with
`python3 -B lib/espeak/tests/test_local_patches.py`. The checks validate the exact
approved local files and unchanged supplied inputs, and reject modified copies
in memory without writing to the supplied checkout. Host sanitizers and bounded
heap measurements do not establish physical R1 behavior or the absence of all
possible leaks.

The 2026-10-21 ordinary-text stability correction also bounds backward
letter-group comparisons in `engine/dictionary.cpp` by the current word.
`engine/translate.cpp` now gives retranslatable Turkish prefixes the required
space boundaries, preserves their complete UTF-8 byte count and derives their
storage from the existing `N_WORD_BYTES` word bound. Explicit rule lengths fit
seven bits; automatically measured prefix lengths occupy the full low byte,
with prefix flags starting at bit eight. A static assertion keeps these length
and storage contracts consistent. The prefix array increases from 41 to 162
bytes; physical-player stack headroom still requires native validation.
`test_backend.c` runs ordinary Turkish, German, Hungarian, Polish and English
text, long UTF-8 filenames, complete-prefix traces and existing character
speech. Its `text-prefixes` mode selects this regression alone. Both existing
hosted test runners also include it in their normal backend run, while the
existing supplied r34 PCM reference corpus remains unchanged. Original supplied
engine sources, dictionaries and linguistic data remain unchanged.
`test_native_backend.c` also exercises the same Turkish sentence and long names
through the bounded native adapter in `run_native_tests.py`.

The local compiler cleanup also frees each completed rule group's temporary
allocations in `engine/compiledict.cpp`; this third source correction is pinned
in `LOCAL-PATCHES.json`. `tests/test_dictionary_ownership.py` executes the
already linked hosted dictionary compiler with leak checking enabled for ASan,
verifies its process result and records that supplied input files remain intact.
The regression fails on the original compiler's 706 leaked rule allocations and
passes after cleanup without changing generated bytes.

For the Linux dictionary equivalence test only, `run_native_tests.py` defines
`ESPEAK_DICTIONARY_WINDOWS_CASE_COMPAT` on the existing source-compiler fixture
and links `--wrap=iswupper`. The actual supplied Windows UCRT classifies exactly
U+1C90 through U+1CB0, 33 Georgian characters, as not uppercase. Independent
execution of the actual Windows dictionary compiler produced the exact supplied
38350-byte dictionary, SHA256
`4ba408bc999a1a63e68ce610dbecd956fd989467c2202e58f4a6dae03def5217`.
The test-only Linux wrapper reproduces that classifier and asserts all 33 inputs
were encountered; every other character delegates to actual libc. Product
Unicode behavior, linguistic rules and supplied data remain unchanged. Strict
full generated/supplied dictionary byte comparison remains mandatory. The earlier
raw Linux locale mismatch and LeakSanitizer failures are retained separately as
diagnostic evidence.
