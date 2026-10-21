# HiBy R1: network services, NAS streaming and emulation feasibility

Research updated: **2026-10-19**. [Polski](HIBY-R1-NETWORK-EMULATION-PL.md).
This is a feasibility guide, not an announcement of new working features.
No NAS/account connection, network playback, emulator execution or physical
R1 test was performed for this research. Vendor-image, emulator and branch
evidence below remains from **2026-10-15**; the new review covers networking
source paths and official radio/podcast/library requirements.

## 1. What is available now

HiBy specifies X1600E, 64 MB RAM, Linux 4.4.94 and 2.4 GHz Wi-Fi, with
DLNA, AirPlay, Wi-Fi import and internet radio in its own software. These do not
automatically become Rockbox features. Wi-Fi import is also different from
playing a remote file without downloading it first.
[HiBy specification](https://guide.hiby.com/en/docs/products/audio_player/hiby_r1/spec/),
[vendor manual](https://guide.hiby.com/en/docs/products/audio_player/hiby_r1/guide/).

In the inspected R1 tree, playback opens a filesystem path, obtains its size
and seeks within it. Playlists format filesystem paths; putting an HTTP or
SMB address into an `.m3u8` does not add the missing transport. There is no
implemented address/user/password NAS workflow in this reviewed R1 code.
This statement concerns this build, not every Rockbox target or external fork.
[Audio buffering](../apps/buffering.c), [playlist handling](../apps/playlist.c),
[hosted filesystem](../firmware/target/hosted/filesystem-unix.c).

**Current source fact:** the connectivity worker persists requested Wi-Fi/BT
and airplane settings, reports observed radio states and supports cancellation.
The hosted backend handles WLAN rfkill/interface state and R1 SDIO reattachment.
This does not supply SSID selection, association/DHCP/DNS management or an
HTTP audio source. An interface being UP does not establish internet access;
the simulator reports unavailable radios rather than controlling host Wi-Fi.
[Connectivity](../apps/hiby_connectivity.c),
[hosted WLAN control](../firmware/target/hosted/hiby/power-control-hiby.c).

The retained modified 1.8b2 vendor image contains `cywdhd.ko`, WLAN firmware,
`wpa_supplicant`, `wpa_cli`, DHCP scripts, curl/OpenSSL libraries and an
SMB-labelled login layout. **Static evidence only:** filenames and layouts do
not establish a usable vendor NAS API, negotiated SMB version, TLS capability
or compatibility with your NAS. The examined image is not a measurement of
your installed firmware. Its scripts use differing configuration paths and
some stop all supplicant/DHCP processes; they cannot be adopted blindly.
No vendor service was run. [Existing firmware inspection context](HIBY-R1-FIRMWARE.md).

## 2. Proposed NAS access and staged network services

**NAS design proposal:** after shared Wi-Fi management, add one read-only NAS
transport. The radio-first service sequence is below. A NAS profile needs
protocol, address, port, share/base directory,
username and password; SMB may additionally need a domain. An IP alone does
not identify the service. For example, `https://nas.example/music/` is an
illustrative HTTPS base address, not a server tested here. Wi-Fi credentials
and NAS credentials are separate.

| Route | Required work and tradeoff | Assessment for R1 |
| --- | --- | --- |
| HTTPS file service | Authenticated file GET; a manifest or listing API for browsing; byte ranges for seeking | Best first streaming prototype if the NAS provides a suitable endpoint; an arbitrary web page is insufficient |
| WebDAV over HTTPS | Bounded `PROPFIND` parsing for directories, then GET/ranges for audio; handle namespaces, escaping and per-item errors | Practical candidate for browsing by address/user/password; NAS support must be checked |
| SMB2/SMB3 | Dedicated client for share listing, authentication and offset reads; signing/encryption policy and reconnects | Feasible research route using a small userspace client such as libsmb2; port size, ABI and performance unmeasured |
| CIFS or FUSE mount | Kernel support, mount permissions, helper and credentials lifecycle, bounded blocking I/O | Could expose local-looking paths, but the image's libfuse alone proves none of these; kernel CIFS support unverified |
| Download to microSD, then play | Complete download, capacity/error checks, then existing local playback | Simpler first transfer feature; explicitly **not streaming** |

Protocol basis: [HTTP range semantics](https://www.rfc-editor.org/rfc/rfc9110.html#section-14),
[WebDAV PROPFIND](https://www.rfc-editor.org/rfc/rfc4918.html#section-9.1),
[pinned libsmb2 API](https://github.com/sahlberg/libsmb2/blob/4cce7691d2281dc9ecf0e5fa4d8d2f4860031df2/README).
These assessments are engineering inferences, not implemented support.

True streaming needs a source abstraction below playback/metadata access:
open, known/unknown length, bounded read, supported seek, cancel and close.
A background worker should
feed a bounded buffer without blocking speech/input. Tag reads at the end of
a file and codec seeks must work too. HTTP range support must be tested using
actual responses; a server may ignore Range. Validate `206`/`Content-Range`,
handle `200`/`416`, and avoid joining bytes from different file revisions.
Live radio and adaptive HLS require additional work; neither follows from
supporting ordinary remote files.
[HTTP responses and validators](https://www.rfc-editor.org/rfc/rfc9110.html).

For Wi-Fi, first establish which process owns the radio, association and DHCP
on the exact firmware, its control socket/permissions and supported security.
Reusing supplicant command/event connections is a candidate, not a verified
R1 integration. The official Doxygen page is labelled 2.5; verify commands
against the installed daemon. Track association, IP lease, DNS and service
reachability separately. Preserve vendor profiles and power/BT/USB behaviour;
avoid competing managers, blanket process termination and vendor startup
scripts. New application profiles belong under `.rockbox`, not in overwritten
vendor configuration.
[Supplicant control interface](https://w1.fi/wpa_supplicant/devel/ctrl_iface_page.html).

### 2.1. Radio first, then podcasts

**Proposed stages; none is implemented or accepted here:**

| Stage | Smallest useful experiment | Required evidence before claiming support |
| --- | --- | --- |
| Shared foundation | Firmware-compatible Wi-Fi manager and one bounded HTTP/TLS worker | Ownership/security inventory; synthetic timeout, redirect, cancellation and memory-pressure tests |
| Internet radio | One authorized direct MP3 URL, then ICY metadata | Actual non-seekable decoding, speech/input responsiveness, loss/reconnect and bounded buffer behavior |
| Podcasts | Public RSS enclosure download to microSD, then local playback; Atom next | Feed/storage failure tests, verified transfer resume and independent playback bookmarks |
| Accessible libraries | Bookshare or DZDN only with authorized API access and supported formats | Provider agreement/login contract, eligible reader, lawful format fixtures and accessible navigation |

For live radio, unknown length and temporary starvation must not be treated
as an ordinary file's size/EOF. Stop closes the connection; reconnect returns
to live. Any pause buffer is finite, not unlimited timeshift or seeking.
Downloading a complete file first is useful transport validation, **not live
streaming**. Bound playlist wrappers/redirects; a station web page is not audio.

Strip ICY metadata framing before decoding, validate `icy-metaint` and preserve
parser state across split reads; test legacy `ICY 200 OK` explicitly. Sanitize
titles and avoid flooding Talkbox; optional automatic announcements need a
persisted switch. Existing MP3/AAC/Ogg code is reusable, but file-size/seek
assumptions still need review. Test AAC-ADTS, MP4/M4A and Ogg Vorbis/Opus
separately. HLS adds playlist refresh, segments/demux, timestamps,
discontinuities and optional protection; defer it to a separate later stage.
[Official ICY client reference](https://www.ffmpeg.org/ffmpeg-protocols.html#http),
[codec registration](../lib/rbcodec/metadata/metadata.c),
[HLS baseline](https://www.rfc-editor.org/rfc/rfc8216.html),
[current HLS guidance](https://developer.apple.com/streaming/hls-authoring-specification-for-apple-devices.html).

For podcasts, parse RSS `enclosure` and later Atom `link rel="enclosure"`
with bounded XML depth/bytes/entries, no external entity/resource loading,
and stable episode IDs rather than titles. Use `.part` files and a recoverable
journal; validate actual byte counts, space, card removal, large-file limits
and short writes before atomically publishing a completed file. Resume only
the same representation with a strong validator and validated `206`/
`Content-Range`; a full `200` must restart, never append. Handle `416` and
changed/expired URLs. Download position and playback bookmark are separate.
Private paid feeds require their own permitted credential workflow.
[RSS specification](https://www.rssboard.org/rss-specification),
[Atom enclosures](https://www.rfc-editor.org/rfc/rfc4287.html#section-4.2.7),
[HTTP validators/ranges](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.5).

### 2.2. Later Bookshare access

**Published facts:** Bookshare documents API v2; its developer notice makes
new-partner admission conditional on ongoing improvements. Contact
`partner-support@bookshare.org` for application approval/key. A verified qualifying
print disability and country/title rights are separate requirements, not granted
by an API key. The v2 reference, version 13.12.0 of 2026-10-07, supplies
format/download links; packaging can return `202`, then `302`, or `429`.
[Developer notice](https://apidocs.bookshare.org/),
[API v2](https://apidocs.bookshare.org/reference/index.html),
[eligibility](https://www.bookshare.org/help-and-learning-articles/who-qualifies-for-bookshare),
[global rights](https://www.bookshare.org/global).

OAuth code/refresh and Bearer authorization are documented; password grant
requires special client approval, and implicit is unsupported. No device-code
or PKCE contract was found on the reviewed authorization page. **Proposal:**
agree an accessible R1/companion login and native-client secret policy with
Bookshare first. Preserve notices, user binding and fingerprints/watermarks;
the DRM policy also describes encryption. Confirm authorized package handling,
rather than assuming unrestricted or universally DRM-free downloads.
[Authorization](https://apidocs.bookshare.org/auth/index.html),
[DRM policy](https://www.bookshare.org/legal/digital-rights-management).

### 2.3. Later DZDN access

**Published facts:** DZDN's registration help covers residents of Poland
with a print disability and supporting documentation, followed by online
activation; general terms §22 describe foreign access through authorized
entities. Its 2026-10-07 Android Player announcement and privacy policy §10
confirm an API/token for its own app, versus browser session cookies.
No documented public third-party API/SDK or authorization was found in this
review. This is not evidence that an API or partnership option does not exist.
[Registration help](https://dzdn.pl/jak-zapisac-sie-do-biblioteki/),
[Player announcement](https://dzdn.pl/aplikacja-mobilna-dzdn-player/),
[privacy §10](https://dzdn.pl/polityka-prywatnosci-2/).

**Next step:** ask the online-service administrator for an approved client
contract, authentication lifecycle, limits, formats, offline/expiry rules and
authorized protection handling. General lending terms §13 restrict copying,
processing and third-party sharing. Public portal/help retrieval failed here,
so online-specific terms and DRM remain unverified; do not infer service
absence. DAISY/Czytak/text/MP3 holdings do not establish R1 compatibility.
Do not bypass protection or treat private app interfaces as public permission.
[General terms](https://dzdn.pl/regulamin/),
[official contact](https://dzdn.pl/kontakt/).

### 2.4. Accessible book formats are a separate requirement

Bookshare distinguishes text EPUB/DAISY from generated MP3/DAISY Audio.
Playing audio tracks alone does not provide DAISY chapter/page navigation.
DAISY 2.02 needs NCC/SMIL; DAISY 3 uses package/NCX/SMIL and may include DTBook.
EPUB needs container/package/spine/XHTML/navigation and, where present, media
overlays. Existing plain-text Talkbox reading/bookmarks are reusable pieces,
not a full DAISY/EPUB reader. **Acceptance requirement:** preserve structural
navigation, language and format-aware positions; validate bounded archive/XML
handling and referenced resources, and report unsupported protection clearly.
[Bookshare formats](https://www.bookshare.org/help-and-learning-articles/what-format-are-bookshare-books-available-in),
[DAISY 2.02](https://daisy.org/activities/standards/daisy/daisy-2/daisy-format-2-02-specification/),
[DAISY 3](https://daisy.org/activities/standards/daisy/daisy-3/z39-86-2005-r2012-specifications-for-the-digital-talking-book/),
[EPUB 3.3](https://www.w3.org/TR/epub-33/).

## 3. Credentials and accessible operation

The proposed UI must support spoken PL/EN server profiles, connection status,
browsing, buffering, retry, cancel and disconnect using buttons and gestures.
Password fields must stay masked and must not automatically speak their
contents. Optional hints need a persisted on/off setting; necessary control
names, state and errors remain available.
These requirements also apply to station/episode/library lists and connection
errors. Check keyboard operation, stable focus and actual Windows NVDA
access separately from self-voicing or simulated R1 input.

Use a read-only NAS account. Keep secrets out of addresses, playlists, logs,
process arguments and error messages. Basic authentication requires a secure
transport; Base64 is not encryption. For HTTPS validate both certificate trust
and server identity, including when connecting by IP; check device time and
provide a deliberate trust procedure for a private CA. Never silently disable
verification or forward credentials to another host after a redirect.
[HTTP Basic](https://www.rfc-editor.org/rfc/rfc7617.html),
[certificate verification](https://curl.se/libcurl/c/CURLOPT_SSL_VERIFYPEER.html),
[hostname/IP verification](https://curl.se/libcurl/c/CURLOPT_SSL_VERIFYHOST.html),
[credential redirect behaviour](https://curl.se/libcurl/c/CURLOPT_USERPWD.html).

Limit redirect depth/schemes and reject HTTPS downgrade. Keep CA updates and
unset-clock recovery explicit; check target TLS/SNI/cipher/entropy support
instead of relying on vendor library names. Redact tokens, private feed and
signed download URLs in diagnostics. Authentication/DRM restrictions remain
binding even when a media URL can be obtained.
[Redirect policy](https://curl.se/libcurl/c/CURLOPT_FOLLOWLOCATION.html),
[certificate time verification](https://docs.openssl.org/3.5/man1/openssl-verification-options/).

Default to keeping a password only for the session. Persisting it needs an
explicit choice and an honest description of protection on a removable card;
an encryption key stored alongside the encrypted password is not meaningful
protection against reading that card. Configuration, cache and logs belong
under the application's own `.rockbox` directory. File permissions alone
cannot be assumed to protect secrets on FAT/exFAT. SMB must not silently fall
back to SMB1 or guest access; negotiate and test the requested signing and
encryption policy. The vendor library filenames do not prove any such policy.

## 4. Memory, power and acceptance tests

The local CPU setting is 1,008 MHz. The current build reserves a 15 MiB core
arena from a configured 16 MiB budget and has a 2 MiB plugin buffer; these
figures are not additional free physical RAM. Linux, services, codecs, speech,
framebuffers, TLS and any emulator share the physical 64 MB. Do not change
the arena to 64 MB on the strength of the hardware specification.
[R1 configuration](../firmware/export/config/hibyr1.h),
[build memory](../tools/configure), [plugin buffer](../firmware/export/config/hibylinux.h),
[arena allocation](../firmware/core_alloc.c).

**Proposed worker safeguards:** use a separate transfer worker, fixed buffers,
bounded headers/metadata/queues, backpressure and sleeping waits. Keep network
I/O outside UI/radio-control locks. Cancellation generations must reject late
callbacks; airplane/USB/shutdown must stop and close owned transfers before
radio teardown, without reconnect overriding user intent. Verify bounded DNS,
connect/TLS/read-idle deadlines. Libcurl multi is a candidate, but standard DNS
can still block with `NOSIGNAL`, and pause can retain internal buffers. Start
with one HTTP/1.1 transfer and no automatic content decompression; count TLS,
resolver/thread/decoder and library allocations as well as the audio ring.
[Multi interface](https://curl.se/libcurl/c/libcurl-multi.html),
[DNS limitation](https://curl.se/libcurl/c/CURLOPT_NOSIGNAL.html),
[pause memory](https://curl.se/libcurl/c/curl_easy_pause.html).

Calculated examples, not throughput measurements: uncompressed stereo
44.1 kHz/16-bit audio is 176,400 B/s (1.4112 Mbit/s); 192 kHz/24-bit is
1,152,000 B/s (9.216 Mbit/s). Eight seconds requires about 1.35 or 8.79 MiB
respectively, before overhead. Compressed files have different rates. Larger
buffers reduce sensitivity to stalls but consume scarce RAM; microSD caching
adds writes. Wi-Fi, TLS, speech and CPU load can reduce battery life; no
runtime, temperature or Wi-Fi/BT coexistence result is available here.

Acceptance must separately test association/DHCP/DNS, wrong password, TLS
failure, directory browsing, Unicode names, metadata, start/seek/pause/resume,
NAS sleep, server-file changes, Wi-Fi loss/reconnect and cancellation. Compare
decoded output with a legal local reference, measure peak RSS/PSS and
`MemAvailable`, underruns and battery with screen off, and verify speech plus
music and BT/USB transitions on an actual R1. A Windows simulator or static
inspection cannot establish these results. Your NAS model, firmware,
protocol/authentication policy and exact R1 firmware remain unknown.
Extend acceptance to stalled DNS/TLS, wrong clock/CA, redirects leaking secrets,
split/malformed ICY, rapid cancellation/stale replies and interrupted podcast
downloads. Choose buffer caps only after measuring process/system headroom
under decoding plus Talkbox, control latency and underruns. Compare measured
idle/active power and battery behavior with known radio/screen states; this
guide supplies no new CPU, free-RAM, throughput or battery estimate.

## 5. Emulation ceiling

Clock frequency alone does not compare different CPU architectures. R1 needs
a 32-bit MIPS Linux executable with the correct ABI; Windows EXE, Android APK
and ARM binaries are not interchangeable. The following are conclusions from
source/requirements, **not R1 benchmarks**.

| System | Primary evidence | R1 assessment |
| --- | --- | --- |
| GB/GBC | Bundled [Rockboy](../apps/plugins/rockboy/README) targets GB/GBC | Existing emulator family; not GBA, and not proof that each game is accessible |
| GBA | [gpSP README](https://github.com/libretro/gpsp/blob/5819380c2ffb0900219d700a382ee68c464ebb99/README.md) and [MIPS build](https://github.com/libretro/gpsp/blob/5819380c2ffb0900219d700a382ee68c464ebb99/Makefile) provide a MIPS dynarec | Credible first experiment, with a frontend, matching ISA/float ABI and tested JIT/cache handling; speed, audio, RAM and battery unknown |
| Nintendo DS | [melonDS CMake](https://github.com/melonDS-emu/melonDS/blob/906e9ebb27da8c6a715cd7abab4abfe8a8d29427/CMakeLists.txt) enables JIT for x86-64/ARM64; [DeSmuME build](https://github.com/libretro/desmume/blob/95b4d798731caa809125b6c3c11d17cc332ff6ef/desmume/src/frontend/libretro/Makefile.libretro) has x86 and 32-bit ARM JIT paths, not a MIPS backend | No demonstrated practical route with these engines on R1; an interpreter experiment is not ruled out, but usable speed is unproven and not a promised feature |
| Nintendo 3DS | [Azahar requirements](https://github.com/azahar-emu/azahar/blob/68202bc4ff7edf9d7280ec0dcd6572b7cd1ae26e/README.md) specify x86-64/ARM64, 2 GB RAM and suitable graphics; [old-model main RAM](https://github.com/azahar-emu/azahar/blob/68202bc4ff7edf9d7280ec0dcd6572b7cd1ae26e/src/core/memory.h) is 128 MiB | Outside a realistic R1 target; shrinking menus or installing Lua does not remove CPU, memory and graphics requirements |
| Wii/GameCube | [Dolphin build](https://github.com/dolphin-emu/dolphin/blob/8d2ad1a662472955497e5bb79d7b9ec6999e1f0d/CMakeLists.txt) normally targets x86-64/ARM64; [FAQ](https://dolphin-emu.org/docs/faq/) recommends 2 GB RAM | Outside a realistic R1 target; its generic no-JIT build option is not evidence of a usable MIPS/64 MB port |

DS also needs two screens, touch and more controls; a portrait display alone
does not solve emulation cost or accessible input. Performance of an ARM
handheld cannot be transferred to R1's MIPS CPU. No ROM or BIOS was downloaded.

## 6. Lua and accessible Pokémon are different requirements

Rockbox Lua is **5.1.5 with integer `long` numbers**, reduced libraries and
Rockbox APIs. It is useful for Rockbox scripts; it is not a GBA emulator or
the emulator-memory API expected by an accessibility script. Its existing
`rb.talk_spell` can reach our TTS path, but a separately launched emulator
does not automatically inherit Rockbox's speech queue or audio mixing.
[Lua configuration](../apps/plugins/lua/luaconf.h),
[Lua bindings](../apps/plugins/lua/rocklib.c), [speech path](../apps/talk.c).

The public [Pokemon Access 3.1.0 revision](https://github.com/nuive/pokemon-access/tree/2deb98f38a4e6674ff60af6f9419be22865f1f39)
still targets VBA-ReRecording. It needs memory/register access, execution and
DMA-write hooks, frame scheduling and PC-style input; also FFI, Windows speech,
dialogs and audio adapters. Its GBA identification reads **32 MiB into Lua**
and makes another FFI buffer: those raw payloads alone reach 64 MiB, before
table overhead or the emulator. Replace this with a compatible streaming or
native CRC implementation, preserving the exact emulated range semantics.
Its listed GBA game data covers English/Spanish; Polish support is not established.
[Requirements](https://github.com/nuive/pokemon-access/blob/2deb98f38a4e6674ff60af6f9419be22865f1f39/readme.md),
[GBA hooks and CRC](https://github.com/nuive/pokemon-access/blob/2deb98f38a4e6674ff60af6f9419be22865f1f39/gba.lua).

**Inference:** gpSP is the stronger initial speed candidate, but has no
compatible Pokemon Access host in the inspected code. mGBA is the better
API-adaptation candidate; the inspected source has debugger-gated breakpoints
and watchpoints, beyond the older public API page. It still needs a small
script-enabled frontend, compatible buffer/register/callback semantics,
speech/effects adapters, accessible controls and save/reset regression tests.
Neither candidate is accepted on R1. Exact game, ROM revision/language,
script version and redistribution permission must be established first.
[mGBA scripting source](https://github.com/mgba-emu/mgba/blob/143adf5aa2a60c6036810b0cd72445e13d74b0e6/src/core/scripting.c),
[script build options](https://github.com/mgba-emu/mgba/blob/143adf5aa2a60c6036810b0cd72445e13d74b0e6/CMakeLists.txt).

## 7. A later contribution to Bahusoid

The 2026-10-15 read-only GitHub inspection found default branch **`Mod25.12.07`**, commit
`059809d123a5b2d4ff1d65b571e99cf56b35dd51`. Branch `Mod26.01.16` also exists;
its name does not establish the intended PR base. The R1 release tag
`x1600_hiby_v2` points to `94c69704e9cf8bae77240a98a8eb7bd5c576f426`.
[Branches API](https://api.github.com/repos/bahusoid/rockbox/branches?per_page=100),
[release tag](https://api.github.com/repos/bahusoid/rockbox/git/ref/tags/x1600_hiby_v2).

For a later proposal, recheck the base with the maintainer, use a clean topic
branch and select only reviewed changes. Separate speech/core accessibility,
R1 input/backend fixes, networking and any standalone emulator work into
reviewable patches with PL/EN docs and regression evidence. Do not propose
the whole dirty development tree or private firmware fixtures. Acceptance
is the maintainer's decision. Nothing was committed, pushed or submitted here.

Licensing must follow each component. Our new bridge work is GPL-2.0-or-later;
the supplied eSpeak engine remains GPL-3.0-or-later and cannot be relabelled
GPLv2. Review the combined distribution, imported files and corresponding
source/build material separately. gpSP carries GPL terms; mGBA is MPL-2.0;
libsmb2 is LGPL-2.1. These do not license vendor firmware, game ROMs/BIOS or
Pokemon Access: no explicit licence was found in its inspected tree.
[Bridge/engine provenance](../lib/espeak/README.md),
[gpSP notice](https://github.com/libretro/gpsp/blob/5819380c2ffb0900219d700a382ee68c464ebb99/main.h),
[mGBA licence](https://github.com/mgba-emu/mgba/blob/143adf5aa2a60c6036810b0cd72445e13d74b0e6/LICENSE),
[libsmb2 licences](https://github.com/sahlberg/libsmb2/blob/4cce7691d2281dc9ecf0e5fa4d8d2f4860031df2/COPYING).

The fork's [contribution text](https://github.com/bahusoid/rockbox/blob/059809d123a5b2d4ff1d65b571e99cf56b35dd51/docs/CONTRIBUTING)
asks for real-name credit and follows Rockbox style. Official upstream uses
Gerrit and its [current policy](../docs/CONTRIBUTING) strongly discourages
AI-generated code and requires provenance if submitted. Disclose actual
assistance and obtain human review; a fork PR does not establish upstream
acceptance or resolve authorship/licensing questions.

## 8. What remains to establish

Before implementation, establish the exact R1 firmware, NAS model and enabled
protocol/port/share, authentication/TLS policy and desired browsing/seek
behaviour, without publishing passwords. For accessible emulation, identify
the exact game/script and required controls first. For radio/podcasts, agree
the permitted source URLs and pause/offline behavior; library integration
also needs provider authorization, an approved login and supported formats.
Hardware trials remain
necessary for networking, synthesis, memory pressure, gameplay and battery;
this research validates none of those runtime outcomes.
