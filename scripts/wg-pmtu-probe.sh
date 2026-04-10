#!/bin/bash
#
# wg-pmtu-probe.sh
#
# Probe Path MTU for each active WireGuard peer.
#
# Writes /var/lib/wg-pmtu/state.json with one entry per peer.
#
# Discovery strategy per peer (see probe_pmtu()):
#   1. Kernel route cache via `ip route get <endpoint>` — zero new packets.
#   2. `tracepath -n <endpoint>` (timeout 8s) — dedicated PMTU discovery.
#   3. Ping bisection with `ping -c 1 -W 1 -M do -s <size>` across a
#      fixed set of MTU candidates.
#   4. Egress interface MTU as an upper-bound fallback.
#
# Peers are probed in parallel (up to PROBE_PARALLEL at a time) via
# `xargs -P`, which drops wall-clock time on a full run from tens of
# minutes (sequential) to roughly ceiling(num_peers / PROBE_PARALLEL) *
# avg-probe-time.
#
# State file writes are serialized with the Python on-demand writer in
# dashboard.py via an fcntl lock on /var/lib/wg-pmtu/state.lock, and are
# atomic (tempfile + rename).

set -euo pipefail

STATE_DIR="/var/lib/wg-pmtu"
STATE_FILE="${STATE_DIR}/state.json"
LOCK_FILE="${STATE_DIR}/state.lock"
PROBE_PARALLEL="${PROBE_PARALLEL:-8}"

mkdir -p "$STATE_DIR"

# Serialize with the Python on-demand writer.
exec 9>"$LOCK_FILE"
flock -x 9

WORK_DIR="$(mktemp -d -p "$STATE_DIR" .probe.XXXXXX)"
TMP_FILE="$(mktemp -p "$STATE_DIR" .state.XXXXXX.json)"
trap 'rm -rf "$WORK_DIR" "$TMP_FILE"' EXIT

TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
now=$(date +%s)

# -------------------------------------------------------------------
# probe_pmtu IP
#   → echoes "<pmtu> <source>" where source is kernel|tracepath|ping|egress|none
probe_pmtu() {
    local ip="$1"
    local kernel_mtu

    # 1. Kernel route cache
    kernel_mtu=$(ip route get "$ip" 2>/dev/null | grep -oP 'mtu \K\d+' | head -1 || true)
    if [ -n "$kernel_mtu" ]; then
        echo "$kernel_mtu kernel"
        return
    fi

    # 2. tracepath (grep pipelines get || true because pipefail would otherwise
    #    abort the whole script when there's no match)
    if command -v tracepath >/dev/null 2>&1; then
        local tp_out tp_mtu
        tp_out=$(timeout 8 tracepath -n "$ip" 2>&1 || true)
        tp_mtu=$(echo "$tp_out" | grep -oP 'Resume:\s*pmtu \K\d+' | tail -1 || true)
        if [ -z "$tp_mtu" ]; then
            tp_mtu=$(echo "$tp_out" | grep -oP 'pmtu \K\d+' | tail -1 || true)
        fi
        if [ -n "$tp_mtu" ] && [ "$tp_mtu" -gt 0 ]; then
            echo "$tp_mtu tracepath"
            return
        fi
    fi

    # 3. Ping bisection
    local sizes=(1472 1452 1432 1412 1392 1372 1292 1272)
    for sz in "${sizes[@]}"; do
        if ping -c 1 -W 1 -M do -s "$sz" "$ip" >/dev/null 2>&1; then
            echo "$((sz + 28)) ping"
            return
        fi
    done

    # 4. Egress interface MTU fallback
    local egress emtu
    egress=$(ip route get "$ip" 2>/dev/null | grep -oP 'dev \K\S+' | head -1 || true)
    if [ -n "$egress" ]; then
        emtu=$(ip link show "$egress" 2>/dev/null | grep -oP 'mtu \K\d+' | head -1 || true)
        if [ -n "$emtu" ]; then
            echo "$emtu egress"
            return
        fi
    fi

    echo "null none"
}
export -f probe_pmtu

# Worker invoked once per peer by xargs -P. Takes a pipe-delimited line
# "iface|pubkey|endpoint|age" and writes a JSON fragment (without leading
# comma) to $WORK_DIR/<safe-filename>.
probe_one_peer() {
    local line="$1"
    local work_dir="$2"
    local iface pubkey endpoint age
    IFS='|' read -r iface pubkey endpoint age <<<"$line"

    # Split host/port — handle IPv4, [IPv6]:port, and [fe80::1%eth0]:port
    local ep_ip
    if [[ "$endpoint" =~ ^\[([^]]+)\]:([0-9]+)$ ]]; then
        ep_ip="${BASH_REMATCH[1]}"
    elif [[ "$endpoint" =~ ^([^:]+):([0-9]+)$ ]]; then
        ep_ip="${BASH_REMATCH[1]}"
    else
        return 0
    fi

    local pmtu source
    read -r pmtu source < <(probe_pmtu "$ep_ip")
    local pmtu_json="${pmtu}"
    [ "$pmtu" = "null" ] && pmtu_json="null"

    local imtu imtu_json
    imtu=$(cat "/sys/class/net/${iface}/mtu" 2>/dev/null || true)
    imtu_json="${imtu:-null}"

    # Derive a safe filename from the public key (base64 has / and + which
    # are unfriendly in filenames).
    local safe_name
    safe_name=$(echo -n "$pubkey" | tr '/+=' '___' | head -c 60)

    printf '    "%s": { "iface": "%s", "iface_mtu": %s, "endpoint": "%s", "pmtu": %s, "source": "%s", "handshake_age_sec": %d }' \
        "$pubkey" "$iface" "$imtu_json" "$endpoint" "$pmtu_json" "$source" "$age" \
        > "$work_dir/$safe_name"
}
export -f probe_one_peer

# -------------------------------------------------------------------
# Build the peer list to probe. Only active peers (with endpoint and
# handshake within the last 10 minutes).
peer_list=$(
    wg show all dump 2>/dev/null | while IFS=$'\t' read -r iface c2 c3 c4 c5 c6 c7 c8 c9; do
        # Interface lines have empty c9 — skip them.
        [ -z "${c9:-}" ] && continue
        local_pub="$c2"
        local_ep="$c4"
        local_hs="$c6"
        [ "$local_ep" = "(none)" ] || [ -z "$local_ep" ] && continue
        [ "$local_hs" = "0" ] && continue
        local_age=$((now - local_hs))
        [ "$local_age" -gt 600 ] && continue
        echo "${iface}|${local_pub}|${local_ep}|${local_age}"
    done
)

# Run probes in parallel. xargs -P N spawns up to N workers; each worker
# invokes probe_one_peer for one pipe-delimited peer line.
if [ -n "$peer_list" ]; then
    echo "$peer_list" | xargs -I {} -P "$PROBE_PARALLEL" \
        bash -c 'probe_one_peer "$1" "$2"' _ {} "$WORK_DIR"
fi

# Assemble the final JSON by concatenating all worker output files.
{
    echo "{"
    echo "  \"generated_at\": \"${TS}\","
    echo "  \"peers\": {"
    first=1
    for f in "$WORK_DIR"/*; do
        [ -e "$f" ] || continue
        if [ $first -eq 0 ]; then
            echo ","
        fi
        first=0
        cat "$f"
    done
    echo ""
    echo "  }"
    echo "}"
} > "$TMP_FILE"

# Validate JSON before swap (cheap guard against any formatter slip).
if ! python3 -m json.tool "$TMP_FILE" >/dev/null 2>&1; then
    echo "ERROR: generated invalid JSON" >&2
    cat "$TMP_FILE" >&2
    exit 1
fi

chmod 644 "$TMP_FILE"
mv "$TMP_FILE" "$STATE_FILE"
# Don't let trap remove the file we just swapped in.
TMP_FILE=""

count=$(python3 -c "import json; print(len(json.load(open('$STATE_FILE'))['peers']))")
echo "wg-pmtu-probe: probed ${count} peers at ${TS} (parallel=${PROBE_PARALLEL})" >&2
