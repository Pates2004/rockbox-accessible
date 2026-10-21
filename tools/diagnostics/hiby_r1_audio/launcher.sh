#!/bin/sh
directory=/data/mnt/sd_0/.rockbox
log="$directory/r1-audio-launcher.log"
program=/tmp/rockbox-r1-audio-diagnostic.r1
umask 077
{
    echo 'R1 audio diagnostics v1: no settings reset, no firmware flash'
    for source in /proc/asound/cards /proc/asound/pcm /sys/class/switch/headset/state /sys/class/switch/balance/state
    do
        echo "--- $source"
        if [ -r "$source" ]; then /bin/cat "$source"; else echo unavailable; fi
    done
} >> "$log"
if ! /bin/cp "$directory/rockbox.r1.audio-original" "$program"; then
    echo 'Cannot stage original application' >> "$log"
    exit 70
fi
if ! /bin/chmod 700 "$program"; then
    echo 'Cannot make original application executable' >> "$log"
    exit 71
fi
LD_LIBRARY_PATH="$directory"
LD_PRELOAD="$directory/r1-audio-trace.so"
export LD_LIBRARY_PATH LD_PRELOAD
exec "$program" >> "$log" 2>&1
