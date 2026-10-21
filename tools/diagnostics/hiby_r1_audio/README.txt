HiBy R1: reversible wired-audio silence diagnostics

This is NOT a confirmed audio fix. It is a separate reversible diagnostic kit.
BUILD.json identifies the application version; manifest.json pins its required
SHA256. Other versions are refused; do not force installation. Logging itself
does not modify the core, Windows simulator or vendor firmware.
Do not copy r1.upt or flash again.

Requires native Windows PowerShell 5.1. Use the Windows terminal and keyboard;
no player-screen transcription is required. Actual NVDA/R1 acceptance is not
claimed. Shut down R1 and put its card in a PC reader before any operation.
E:\ is an example; substitute the actual card drive.

Run from this kit directory:
  .\Start.cmd -Mode Check -CardRoot E:\
This reads the card and creates Reports/<timestamp>/report.json locally.
It can identify a different application/library or saved speech settings.

To capture actual native audio failures:
  .\Start.cmd -Mode Enable -CardRoot E:\
Confirm YES. Only the exact alpha7 application and ALSA hashes are supported;
a different/incomplete build is refused rather than overwritten.
Safely eject the card, insert it into the powered-off R1, connect wired
headphones and boot. Wait about 15 seconds and try a few short button presses.
Diagnostics do not raise or force the volume. Shut down before removing card.

Put the card back in the PC reader:
  .\Start.cmd -Mode Collect -CardRoot E:\
Send report.json, r1-audio-diagnostic.log and r1-audio-launcher.log from the
new Reports subdirectory. No player-screen reading is needed.

To restore ordinary Rockbox with the player off/card in reader:
  .\Start.cmd -Mode Restore -CardRoot E:\
Confirm YES. Restoration does not require working player speech, including
after a failed diagnostic launch, provided the preserved files are intact.

Enable MOVES the original application to rockbox.r1.audio-original on the
same card, without duplicating it. It installs a small tracing library and
shell launcher. At boot the original application is copied to /tmp RAM and
run unchanged with ALSA tracing. Settings, bookmarks, engine data, music,
volume/mixer/routes, Bluetooth/Wi-Fi, partitions, bootloader and vendor firmware
are not modified. Two logs live beside the application. The library trace is
limited to 64 KiB and initial packet metrics, not full audio or spoken text.

Collect makes a useful local log copy and leaves card logs in place. Restore
moves diagnostic launcher/library/logs to Reports for diagnosis/recovery and
restores the exact original application. These user reports/preserved files
remain afterward; no automatic deletion occurs. Only selected speech/volume
settings are collected, not the entire configuration or network passwords.

Controlled MIPS/null-PCM tests cannot establish physical DAC/headset detection,
all firmware compatibility or actual sound. This does not diagnose every TTS
failure. It is not a daily-use release; restore after capturing evidence.
