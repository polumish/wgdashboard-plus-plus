#!/bin/bash
#
# install-pmtu-probe.sh
#
# Install the WGDashboard Path MTU probe on a bare-metal host:
#   - installs iputils-tracepath and mtr-tiny system packages
#   - copies wg-pmtu-probe.sh to /usr/local/bin
#   - installs and enables wg-pmtu-probe.{service,timer}
#   - creates /var/lib/wg-pmtu state directory
#
# Run as root. Safe to re-run — installs are idempotent.
#
# Docker users: nothing to do here; the Dockerfile bakes the same
# packages and script into the image, and the entrypoint runs the probe
# in a background loop.

set -euo pipefail

if [ "$EUID" -ne 0 ]; then
    echo "This installer must be run as root." >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Installing system packages (iputils-tracepath, mtr-tiny)"
if command -v apt-get >/dev/null 2>&1; then
    apt-get update -qq
    apt-get install -y iputils-tracepath mtr-tiny
elif command -v dnf >/dev/null 2>&1; then
    dnf install -y iputils mtr
elif command -v apk >/dev/null 2>&1; then
    apk add --no-cache iputils mtr
else
    echo "WARN: unknown package manager; please install tracepath and mtr manually." >&2
fi

echo "==> Copying wg-pmtu-probe.sh to /usr/local/bin"
install -m 755 "$SCRIPT_DIR/wg-pmtu-probe.sh" /usr/local/bin/wg-pmtu-probe.sh

echo "==> Creating /var/lib/wg-pmtu state directory"
mkdir -p /var/lib/wg-pmtu
chmod 755 /var/lib/wg-pmtu

echo "==> Installing systemd units"
install -m 644 "$SCRIPT_DIR/wg-pmtu-probe.service" /etc/systemd/system/wg-pmtu-probe.service
install -m 644 "$SCRIPT_DIR/wg-pmtu-probe.timer" /etc/systemd/system/wg-pmtu-probe.timer
systemctl daemon-reload

echo "==> Enabling and starting wg-pmtu-probe.timer"
systemctl enable wg-pmtu-probe.timer
systemctl start wg-pmtu-probe.timer

echo
echo "Done. First probe runs at boot+5min; next ones hourly."
echo "Run one now manually:     systemctl start wg-pmtu-probe.service"
echo "View results:             cat /var/lib/wg-pmtu/state.json"
echo "View probe logs:          journalctl -u wg-pmtu-probe.service"
