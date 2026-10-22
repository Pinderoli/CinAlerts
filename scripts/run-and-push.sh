#!/usr/bin/env bash
# Scan, then commit and push whatever changed. Runs on anything with push access to the repo:
# GitHub Actions, a laptop, a Raspberry Pi, a VPS. Extra arguments go to `cinalerts run`.
#
# Each chain's data lives in its own files and is only rewritten when this machine could reach that
# chain, so several runners can share the repo. If another runner pushed in the meantime, we
# re-apply our files on top of theirs (merging the shared lookup cache).
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
RUNNER="${CINALERTS_RUNNER:-$(hostname -s)}"

git pull -q --rebase origin "$BRANCH"
"$PY" -m cinalerts run "$@"

git add docs/data data
if git diff --cached --quiet; then
  echo "No changes to publish."
  exit 0
fi
git commit -q -m "Update listings $(date -u +%F) ($RUNNER)"

for attempt in 1 2 3; do
  if git push -q origin "$BRANCH"; then
    echo "Published."
    exit 0
  fi
  echo "Push rejected (attempt $attempt); re-applying on top of the latest version."
  saved="$(mktemp -d)"
  changed="$(git diff --name-only HEAD~1 HEAD)"
  for f in $changed; do mkdir -p "$saved/$(dirname "$f")"; cp "$f" "$saved/$f"; done
  git fetch -q origin "$BRANCH"
  git reset -q --hard "origin/$BRANCH"
  for f in $changed; do
    if [ "$f" = "data/films.json" ] && [ -f "$f" ]; then
      "$PY" -c 'import json,sys; a=json.load(open(sys.argv[1])); a.update(json.load(open(sys.argv[2]))); json.dump(a,open(sys.argv[1],"w"),indent=1,sort_keys=True,ensure_ascii=False)' "$f" "$saved/$f"
    else
      mkdir -p "$(dirname "$f")"; cp "$saved/$f" "$f"
    fi
  done
  git add docs/data data
  git commit -q -m "Update listings $(date -u +%F) ($RUNNER)"
  sleep $((attempt * 5))
done
echo "Couldn't push after 3 attempts." >&2
exit 1
