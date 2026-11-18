#!/bin/bash
# Record the machine and toolchain a run used, as JSON on stdout.
set -euo pipefail

json() { python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().strip()))'; }

if [[ "$(uname)" == "Darwin" ]]; then
  model=$(sysctl -n hw.model)
  cpu=$(sysctl -n machdep.cpu.brand_string)
  cores=$(sysctl -n hw.ncpu)
  perf=$(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null || echo "")
  memory_gb=$(( $(sysctl -n hw.memsize) / 1073741824 ))
  os="macOS $(sw_vers -productVersion) ($(sw_vers -buildVersion))"
  xcode=$(xcodebuild -version 2>/dev/null | tr '\n' ' ' || echo "")
  power=$(pmset -g batt 2>/dev/null | head -1 || echo "")
else
  model=$(cat /sys/devices/virtual/dmi/id/product_name 2>/dev/null || echo "")
  cpu=$(grep -m1 "model name" /proc/cpuinfo | cut -d: -f2- | xargs)
  cores=$(nproc)
  perf=""
  memory_gb=$(( $(grep MemTotal /proc/meminfo | awk '{print $2}') / 1048576 ))
  os=$(. /etc/os-release && echo "$PRETTY_NAME")
  xcode=""
  power=""
fi

cat <<EOF
{
  "recorded_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "model": $(echo "$model" | json),
  "cpu": $(echo "$cpu" | json),
  "cores": $cores,
  "performance_cores": $(echo "$perf" | json),
  "memory_gb": $memory_gb,
  "os": $(echo "$os" | json),
  "xcode": $(echo "$xcode" | json),
  "swift": $(swift --version 2>&1 | head -1 | json),
  "power": $(echo "$power" | json),
  "harness_commit": "$(git -C "$(dirname "$0")/.." rev-parse HEAD)"
}
EOF
