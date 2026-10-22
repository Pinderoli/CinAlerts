#!/usr/bin/env bash
# Run the daily scan from this Mac (a home IP reaches every chain, unlike GitHub Actions).
#
#   scripts/macos/install.sh <ntfy-topic> [HH:MM]
#
# Uses its own clone in ~/.cinalerts, so it never touches your working copy. Runs daily at the
# given time (default 09:00), or as soon as the Mac wakes if it was asleep then.
# Remove everything with scripts/macos/uninstall.sh.
set -euo pipefail

TOPIC="${1:?usage: install.sh <ntfy-topic> [HH:MM]}"
AT="${2:-09:00}"
HOUR=$((10#${AT%%:*})); MINUTE=$((10#${AT##*:}))
HOME_DIR="$HOME/.cinalerts"
REPO_URL="$(git -C "$(dirname "$0")" remote get-url origin | sed -E 's#^git@github.com:#https://github.com/#')"
GH="$(command -v gh || true)"
LABEL="com.cinalerts.scan"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

[ -n "$GH" ] || { echo "Needs the GitHub CLI (gh) for push access: brew install gh && gh auth login" >&2; exit 1; }

mkdir -p "$HOME_DIR"
if [ ! -d "$HOME_DIR/repo/.git" ]; then
  git clone -q "$REPO_URL" "$HOME_DIR/repo"
fi
# Push using gh's stored login, configured for this clone only.
git -C "$HOME_DIR/repo" config credential.helper "!$GH auth git-credential"
python3 -m venv "$HOME_DIR/venv"
"$HOME_DIR/venv/bin/pip" install -q --upgrade pip
"$HOME_DIR/venv/bin/pip" install -q -r "$HOME_DIR/repo/requirements.txt"

umask 077
cat > "$HOME_DIR/env" <<EOF
NTFY_TOPIC=$TOPIC
PYTHON=$HOME_DIR/venv/bin/python
CINALERTS_RUNNER=$(hostname -s)
EOF

mkdir -p "$(dirname "$PLIST")"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-c</string>
    <string>set -a; . "$HOME_DIR/env"; set +a; exec "$HOME_DIR/repo/scripts/run-and-push.sh"</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string></dict>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>$MINUTE</integer></dict>
  <key>StandardOutPath</key><string>$HOME_DIR/scan.log</string>
  <key>StandardErrorPath</key><string>$HOME_DIR/scan.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed: daily at $AT. Run now with:  launchctl kickstart gui/$(id -u)/$LABEL"
echo "Log: $HOME_DIR/scan.log"
