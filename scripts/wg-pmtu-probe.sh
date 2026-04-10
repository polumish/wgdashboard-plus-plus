#!/bin/bash
# wg-pmtu-probe.sh
#
# Probe Path MTU for each active WireGuard peer.
#
# Writes /var/lib/wg-pmtu/state.json with one entry per peer.
#
# Discovery strategy per peer:
#   1. Kernel route cache via `ip route get <endpoint>` — zero new packets.
#      If the kernel has discovered a reduced MTU, that's our answer.
#   2. Ping-based discovery with `ping -c 1 -W 2 -M do -s <size>`.
#      Start from 1472 (1500 - 28 IP/ICMP headers) and decrement in
#      steps of 28 down to 1272 (1300-28). First size that succeeds
#      gives us path MTU = size + 28.
#   3. If ping is completely blocked, record egress interface MTU as
#      the "best known" upper bound and mark source=egress.
#
# Output format: JSON keyed by peer public key, with fields:
#   iface, endpoint, pmtu, source, handshake_age_sec, iface_mtu
#
# Safe to run hourly via systemd timer. Per peer: 0-5 ping packets.

set -euo pipefail

STATE_DIR="/var/lib/wg-pmtu"
STATE_FILE="${STATE_DIR}/state.json"
LOCK_FILE="${STATE_DIR}/state.lock"

mkdir -p "$STATE_DIR"

# Serialize with the Python on-demand writer (dashboard.py) using flock on
# a sidecar lockfile. Both take LOCK_EX while rewriting the state file.
exec 9>"$LOCK_FILE"
flock -x 9

# Write to a tempfile in the same directory so we can atomically rename
# into place. Cleanup on exit regardless of success.
TMP_FILE="$(mktemp -p "$STATE_DIR" .state.XXXXXX.json)"
trap 'rm -f "$TMP_FILE"' EXIT

TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
now=$(date +%s)

# Get MTU of a WG interface — needed to report "configured" MTU per peer
iface_mtu() {
    ip link show "$1" 2>/dev/null | grep -oP 'mtu \K\d+' | head -1
}

# Discover path MTU to an IP.
# Echoes "<pmtu> <source>" on stdout (source = kernel|tracepath|ping|egress|none)
probe_pmtu() {
    local ip="$1"
    local kernel_mtu
    # 1. Kernel cache — zero new packets
    kernel_mtu=$(ip route get "$ip" 2>/dev/null | grep -oP 'mtu \K\d+' | head -1 || true)
    if [ -n "$kernel_mtu" ]; then
        echo "$kernel_mtu kernel"
        return
    fi
    # 2. tracepath — designed for PMTU discovery, parses final "Resume: pmtu N"
    if command -v tracepath >/dev/null 2>&1; then
        local tp_out tp_mtu
        tp_out=$(timeout 8 tracepath -n "$ip" 2>&1 || true)
        # Prefer the final "Resume: pmtu N" line, fall back to any "pmtu N"
        tp_mtu=$(echo "$tp_out" | grep -oP 'Resume:\s*pmtu \K\d+' | tail -1)
        if [ -z "$tp_mtu" ]; then
            tp_mtu=$(echo "$tp_out" | grep -oP 'pmtu \K\d+' | tail -1)
        fi
        if [ -n "$tp_mtu" ] && [ "$tp_mtu" -gt 0 ]; then
            echo "$tp_mtu tracepath"
            return
        fi
    fi
    # 3. Ping bisection — common MTU sizes
    local sizes=(1472 1452 1432 1412 1392 1372 1292 1272)
    for sz in "${sizes[@]}"; do
        if ping -c 1 -W 1 -M do -s "$sz" "$ip" >/dev/null 2>&1; then
            echo "$((sz + 28)) ping"
            return
        fi
    done
    # 4. Egress interface MTU as upper bound
    local egress
    egress=$(ip route get "$ip" 2>/dev/null | grep -oP 'dev \K\S+' | head -1 || true)
    if [ -n "$egress" ]; then
        local emtu
        emtu=$(ip link show "$egress" 2>/dev/null | grep -oP 'mtu \K\d+' | head -1 || true)
        if [ -n "$emtu" ]; then
            echo "$emtu egress"
            return
        fi
    fi
    echo "null none"
}

echo "{" > "$TMP_FILE"
echo "  \"generated_at\": \"${TS}\"," >> "$TMP_FILE"
echo "  \"peers\": {" >> "$TMP_FILE"

first=1

# wg show all dump:
#   interface line (5 cols):   iface privkey pubkey listen_port fwmark
#   peer line      (9 cols):   iface pubkey psk endpoint allowed_ips latest_handshake rx tx keepalive
while IFS=$'\t' read -r iface c2 c3 c4 c5 c6 c7 c8 c9; do
    if [ -z "${c9:-}" ]; then
        continue  # interface line
    fi

    pub="$c2"
    endpoint="$c4"
    last_hs="$c6"

    if [ "$endpoint" = "(none)" ] || [ -z "$endpoint" ]; then
        continue
    fi
    if [ "$last_hs" = "0" ]; then
        continue
    fi
    age=$((now - last_hs))
    if [ "$age" -gt 600 ]; then
        continue
    fi

    # Strip port (handle IPv6 in brackets)
    # Supported forms: 1.2.3.4:port | [::1]:port | [fe80::1%eth0]:port
    if [[ "$endpoint" =~ ^\[([^]]+)\]:([0-9]+)$ ]]; then
        ep_ip="${BASH_REMATCH[1]}"
    elif [[ "$endpoint" =~ ^([^:]+):([0-9]+)$ ]]; then
        ep_ip="${BASH_REMATCH[1]}"
    else
        continue
    fi

    # Probe
    read -r pmtu source < <(probe_pmtu "$ep_ip")
    if [ "$pmtu" = "null" ]; then
        pmtu_json="null"
    else
        pmtu_json="$pmtu"
    fi

    imtu=$(iface_mtu "$iface")
    imtu_json="${imtu:-null}"

    if [ $first -eq 0 ]; then
        echo "," >> "$TMP_FILE"
    fi
    first=0

    printf '    "%s": { "iface": "%s", "iface_mtu": %s, "endpoint": "%s", "pmtu": %s, "source": "%s", "handshake_age_sec": %d }' \
        "$pub" "$iface" "$imtu_json" "$endpoint" "$pmtu_json" "$source" "$age" >> "$TMP_FILE"

done < <(wg show all dump 2>/dev/null)

echo "" >> "$TMP_FILE"
echo "  }" >> "$TMP_FILE"
echo "}" >> "$TMP_FILE"

if ! python3 -m json.tool "$TMP_FILE" > /dev/null 2>&1; then
    echo "ERROR: generated invalid JSON" >&2
    cat "$TMP_FILE" >&2
    exit 1
fi

mv "$TMP_FILE" "$STATE_FILE"
chmod 644 "$STATE_FILE"

count=$(python3 -c "import json; d=json.load(open('$STATE_FILE'))['peers']; print(len(d))")
echo "wg-pmtu-probe: probed ${count} peers at ${TS}" >&2
