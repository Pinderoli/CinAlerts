#!/usr/bin/env bash
# Remove the scheduled scan and its clone from this Mac.
set -euo pipefail
LABEL="com.cinalerts.scan"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
rm -rf "$HOME/.cinalerts"
echo "Removed."
