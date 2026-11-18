#!/bin/bash
# Run the full study on one subject from subjects/subjects.json.
#   scripts/run-subject.sh swift-argument-parser [count]
# Clones into ../subjects/<name> if needed, records the machine, runs every selector and the real
# tests on `count` commits ending at the pinned commit (plus seeded bugs), then scores the run.
set -euo pipefail

name="$1"
here="$(cd "$(dirname "$0")/.." && pwd)"
subjects_dir="${SUBJECTS_DIR:-$here/../subjects}"
py="${PYTHON:-$here/.venv/bin/python}"

read -r url end default_count pins < <("$py" - "$here/subjects/subjects.json" "$name" <<'EOF'
import json, sys
s = next(x for x in json.load(open(sys.argv[1]))["subjects"] if x["name"] == sys.argv[2])
pins = ",".join(f"{k}={v}" for k, v in s.get("dependency_pins", {}).items())
print(s["url"], s["end_commit"], s["count"], pins or "-")
EOF
)
[[ "$pins" == "-" ]] && pins=""
export TSEL_PINS="$pins"
count="${2:-$default_count}"
out="$here/results/${RUN_TAG:-macos}/$name"
repo="$subjects_dir/$name"

mkdir -p "$subjects_dir" "$out"
if [[ "$url" == local:* ]]; then
  # built on this machine from files in this repository, with reproducible commit hashes
  [[ -d "$repo/.git" ]] || "$py" "$here/${url#local:}" "$repo"
else
  [[ -d "$repo/.git" ]] || git clone --filter=blob:none "$url" "$repo"
  git -C "$repo" fetch -q origin "$end" || true
fi
git -C "$repo" cat-file -e "$end^{commit}"

"$here/scripts/machine.sh" > "$out/machine.json"
echo "$name: $count commits ending at ${end:0:12}; results in $out"
# keep the Mac awake for the whole run
keep_awake=""
command -v caffeinate >/dev/null && keep_awake="caffeinate -dimsu"

$keep_awake "$py" "$here/scripts/study.py" "$repo" "$end" "$count" "$out" 2>&1 | tee -a "$out/run.log"
"$py" "$here/scripts/analyze.py" "$out" | tee "$out/summary.txt"
