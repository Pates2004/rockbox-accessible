#!/bin/sh
set -eu
program_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$program_dir"
runtime_dir="$program_dir/runtime"
mkdir -p "$runtime_dir/cache" "$runtime_dir/config"
export XDG_CACHE_HOME="$runtime_dir/cache"
export XDG_CONFIG_HOME="$runtime_dir/config"
export MESA_SHADER_CACHE_DIR="$XDG_CACHE_HOME/mesa"
export PULSE_COOKIE="$XDG_CONFIG_HOME/pulse-cookie"
if ./rockboxui --root "$program_dir/simdisk" "$@" > "$program_dir/simulator.log" 2>&1; then
    exit 0
else
    result=$?
    cat "$program_dir/simulator.log" >&2
    exit "$result"
fi
