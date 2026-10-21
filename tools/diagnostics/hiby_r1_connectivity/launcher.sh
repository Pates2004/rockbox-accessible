#!/bin/sh
directory=/data/mnt/sd_0/.rockbox
systemroot=
temporary=/tmp
utility=/bin/busybox
controller=/usr/bin/bluetoothctl
umask 077
unset LD_PRELOAD

cleanup()
{
    if [ -n "$work" ]; then
        "$utility" rm -f "$work/snapshot" "$work/show" "$work/program"
        "$utility" rmdir "$work"
    fi
}

read_value()
{
    printf '%s: ' "$1"
    if [ -f "$systemroot$1" ] && [ -r "$systemroot$1" ]; then
        "$utility" dd "if=$systemroot$1" bs=256 count=1 2>/dev/null
        printf '\n'
    else
        printf 'unavailable\n'
    fi
}

read_link()
{
    printf '%s: ' "$1"
    value=$("$utility" readlink "$systemroot$1" 2>/dev/null | "$utility" dd bs=256 count=1 2>/dev/null)
    if [ -n "$value" ]; then printf '%s\n' "$value"; else printf 'unavailable\n'; fi
}

snapshot()
{
    printf 'HiBy R1 passive connectivity snapshot v1; before application\n'
    printf 'No radio commands, credentials, peer lists or settings collected.\n'
    count=0
    for entry in "$systemroot"/sys/class/rfkill/rfkill[0-9]*
    do
        [ -d "$entry" ] || continue
        count=$((count + 1))
        [ "$count" -le 16 ] || break
        relative=${entry#"$systemroot"}
        for field in type name soft hard state
        do
            read_value "$relative/$field"
        done
    done
    printf 'rfkill entries inspected (maximum 16): %s\n' "$count"
    for function in mmc0:0001:1 mmc0:0001:2
    do
        relative="/sys/bus/sdio/devices/$function"
        for field in vendor device class
        do
            read_value "$relative/$field"
        done
        read_link "$relative/driver"
        read_link "$relative/driver/module"
    done
    for interface in wlan0 wlan1
    do
        relative="/sys/class/net/$interface"
        if [ -d "$systemroot$relative" ]; then
            printf '%s exists\n' "$relative"
            read_value "$relative/flags"
        else
            printf '%s absent\n' "$relative"
        fi
    done
    count=0
    for entry in "$systemroot"/proc/[0-9]*/comm
    do
        count=$((count + 1))
        [ "$count" -le 256 ] || break
        [ -f "$entry" ] || continue
        service=$("$utility" dd "if=$entry" bs=32 count=1 2>/dev/null)
        case "$service" in
            bluetoothd|bluetooth|bt_service|bluetooth_servi*|hciattach|brcm_patchram*|bsa_server)
                printf 'running service: %s\n' "$service" ;;
        esac
    done
    read_value /run/r1_wireless_type
    printf '/dev/rfkill metadata: '
    if ! "$utility" stat -c 'type=%F mode=%a major=%t minor=%T' "$systemroot/dev/rfkill" 2>/dev/null; then
        metadata=$("$utility" ls -ldn "$systemroot/dev/rfkill" 2>/dev/null | "$utility" dd bs=512 count=1 2>/dev/null)
        if [ -n "$metadata" ]; then printf 'numeric ls stat fallback: %s\n' "$metadata"; else printf 'unavailable\n'; fi
    fi
    if [ -x "$controller" ] && "$utility" timeout --help >/dev/null 2>&1; then
        printf 'bluetoothctl show (3-second SIGKILL limit, maximum 4096 bytes):\n'
        "$utility" timeout -s KILL 3 "$controller" show 2>/dev/null | "$utility" dd bs=4096 count=1 2>/dev/null
        printf '\n'
    else
        printf 'bluetoothctl show: skipped (no trusted bounded timeout/controller)\n'
    fi
}

original="$directory/rockbox.r1.connectivity-original"
[ -f "$original" ] && [ ! -L "$original" ] || exit 70
checksum=$("$utility" sha256sum "$original") || exit 70
checksum=${checksum%% *}
case "$checksum" in
    7d82d50b88e0bfc3f0fe7bc6882843d047128d5504fc10bbdc72664119058390|a536942c7cc6caa68c6dae24c2128e9d623562e2e26e7df10fdb51539684e122) ;;
    *) exit 70 ;;
esac
work=$("$utility" mktemp -d "$temporary/r1-connectivity.XXXXXX") || exit 71
trap cleanup 0
trap 'exit 72' HUP INT TERM
"$utility" cp "$original" "$work/program" || exit 73
staged=$("$utility" sha256sum "$work/program") || exit 73
[ "${staged%% *}" = "$checksum" ] || exit 73
"$utility" chmod 700 "$work/program" || exit 74

log="$directory/r1-connectivity.log"
if [ ! -e "$log" ] && [ ! -L "$log" ]; then
    snapshot > "$work/snapshot" 2>/dev/null
    if (set -C; : > "$log") 2>/dev/null; then
        "$utility" dd "if=$work/snapshot" "of=$log" bs=65536 count=1 conv=notrunc 2>/dev/null
    fi
fi
"$utility" rm -f "$work/snapshot" "$work/show"
LD_LIBRARY_PATH="$directory"
export LD_LIBRARY_PATH
exec "$work/program" "$@"
