#!/usr/bin/env bash
set -euo pipefail
OWNER="${1:-yuhanyu0}"
REPO="${2:-market-state-observatory}"
VISIBILITY="${3:-public}"
command -v git >/dev/null
command -v gh >/dev/null
gh auth status
[ ! -d .git ] || { echo "Already a git repo; review manually"; exit 1; }
git init -b main
git add .
git commit -m "initial: launch Market State Observatory"
gh repo create "$OWNER/$REPO" --"$VISIBILITY" --source . --remote origin --push
echo "Created https://github.com/$OWNER/$REPO"
