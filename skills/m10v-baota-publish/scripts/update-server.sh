#!/usr/bin/env bash
# Run on the existing Baota host; preserve firmware inputs, settings and venv.
set -Eeuo pipefail
# Sources must remain readable by the www service even when SSH uses umask 077.
umask 022
trap 'printf "RELEASE_ERROR line=%s\n" "$LINENO" >&2' ERR
mode=${1:---check}
expected=${2:-}
bundle=${3:-}
repo=${M10V_DEPLOY_ROOT:-/www/wwwroot/m10v}
node=${M10V_DEPLOY_NODE:-/usr/local/bin/m10v-node}
lock=${M10V_DEPLOY_LOCK:-/var/lock/m10v-deploy.lock}
service=m10v
if [[ "$mode" != --check && "$mode" != --deploy ]]; then
  printf 'Usage: bash update-server.sh --check | --deploy FULL_COMMIT_SHA [GIT_BUNDLE]\n' >&2; exit 2
fi
if [[ "$mode" == --deploy && ! "$expected" =~ ^[0-9a-f]{40}$ ]]; then
  printf 'A full Git commit SHA is required.\n' >&2; exit 2
fi
clean_checkout(){
  local changes
  changes=$(git status --porcelain) || return
  [[ -z "$changes" ]]
}
cd "$repo"
origin=$(git remote get-url origin)
[[ "${origin%.git}" == https://github.com/zhaoo/m10v ]]
clean_checkout || { printf 'Tracked or untracked server changes exist; stop for inspection.\n' >&2; exit 1; }
[[ $(git branch --show-current) == main ]] || { printf 'Server must be on main.\n' >&2; exit 1; }
[[ $(systemctl show "$service" -p User --value) == www ]]
[[ $(systemctl show "$service" -p WorkingDirectory --value) == "$repo" ]]
[[ -x "$node" && -x "$repo/.venv/bin/python" ]]
[[ -r bin/fwdc239b-gr3-official.bin && -r bin/fwdc243b-gr3x-official.bin ]]
systemctl is-active --quiet "$service"
printf 'SERVER_READY commit=%s service=%s\n' "$(git rev-parse HEAD)" "$service"
[[ "$mode" == --deploy ]] || exit 0
exec 9>"$lock"
flock -n 9 || { printf 'Another deployment is running.\n' >&2; exit 1; }
# Recheck after locking, before any mutation.
clean_checkout
if [[ -n "$bundle" ]]; then
  bundle=$(realpath "$bundle")
  git bundle verify "$bundle"
  ref="refs/m10v/releases/$expected"
  git fetch "$bundle" "HEAD:$ref"
else
  fetched=0
  for attempt in 1 2 3; do
    if git -c http.version=HTTP/1.1 -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=20 fetch origin main; then
      fetched=1; break
    fi
    if [[ $attempt -lt 3 ]]; then
      printf 'FETCH_RETRY attempt=%s\n' "$attempt" >&2
      sleep "$((attempt * 5))"
    fi
  done
  [[ $fetched == 1 ]] || { printf 'GitHub fetch failed after three attempts; running version preserved.\n' >&2; exit 1; }
  ref=origin/main
fi
[[ $(git rev-parse "$ref") == "$expected" ]] || { printf 'Fetched release differs from requested SHA; stop.\n' >&2; exit 1; }
git merge-base --is-ancestor HEAD "$expected"
previous=$(git rev-parse HEAD)
work=$(mktemp -d /tmp/m10v-deploy.XXXXXX)
chown www:www "$work"
changed=0
completed=0
active_unit=
cleanup(){
  result=$?
  [[ $completed == 1 || $result -ne 0 ]] || result=1
  trap - EXIT
  if [[ -n "$active_unit" ]]; then
    systemctl stop "$active_unit" || true
  fi
  if [[ $result -ne 0 && $changed == 1 ]]; then
    printf 'Deployment failed; restoring %s\n' "$previous" >&2
    # --keep refuses to discard unexpected concurrent working-tree edits.
    if git reset --keep "$previous" && systemctl restart "$service"; then
      printf 'ROLLBACK_COMMIT=%s\n' "$(git rev-parse HEAD)" >&2
    else
      printf 'Automatic restore failed; inspect service and working tree.\n' >&2
    fi
  fi
  rm -rf -- "$work"
  exit "$result"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
# Flag first so even a failed merge is handled conservatively.
changed=1
git merge --ff-only "$expected"
[[ $(git rev-parse HEAD) == "$expected" ]]
for model in gr3 gr3x gr4; do
  if [[ $model == gr3 ]]; then
    build_args=(scripts/build_gr3_device_candidate.mjs "$work/$model")
  elif [[ $model == gr3x ]]; then
    build_args=(scripts/check_gr3x_release.mjs)
  else
    build_args=(scripts/check_gr4_release.mjs)
  fi
  build_timeout=600
  [[ $model == gr4 ]] && build_timeout=900
  # Bound the entire compiler/Python/Node process tree, not just the JS heap.
  # Reclaim above 600 MiB; cap resident build memory at 700 MiB so the
  # ~1.6 GiB host retains headroom. Swap stays bounded by the existing 1 GiB pool.
  active_unit="m10v-build-${expected:0:12}-$$-$model.service"
  printf 'FIRMWARE_BUILD_START model=%s unit=%s memory_high=600M memory=700M swap=384M timeout=%ss\n' "$model" "$active_unit" "$build_timeout"
  systemd-run --quiet --wait --pipe --collect --unit="$active_unit" \
    --property=MemoryHigh=600M --property=MemoryMax=700M --property=MemorySwapMax=384M \
    --property=CPUQuota=100% --property=TasksMax=64 \
    --property=RuntimeMaxSec="$build_timeout" --property=OOMPolicy=kill \
    --property=KillMode=control-group --property=TimeoutStopSec=10 \
    --working-directory="$repo" -- runuser -u www -- env NODE_OPTIONS=--max-old-space-size=128 M10V_LLVM_CLANG=/usr/bin/clang M10V_PYTHON="$repo/.venv/bin/python" "$node" \
    "${build_args[@]}" >"$work/$model.log" 2>&1 &
  build_pid=$!
  # wait is interruptible, so SSH termination reaches cleanup immediately.
  if ! wait "$build_pid"; then
    cat "$work/$model.log" >&2
    journalctl -u "$active_unit" -n 12 --no-pager >&2 || true
    printf 'FIRMWARE_BUILD_FAILED model=%s (resource limit, timeout or build error)\n' "$model" >&2
    exit 1
  fi
  active_unit=
  if [[ $model != gr3x ]]; then
    printf 'FIRMWARE_BUILD_OK model=%s\n' "$model"
  else
    printf 'MODEL_GUARD_OK model=gr3x native_export=blocked\n'
  fi
done
systemctl restart "$service"
healthy=0
for attempt in {1..10}; do
  if systemctl is-active --quiet "$service" && curl --max-time 5 -fsS http://127.0.0.1:3000/gr3/ -o "$work/page.html"; then
    if "$repo/.venv/bin/python" -c 'from pathlib import Path; import sys; assert "id=\"debug-mode\"" in Path(sys.argv[1]).read_text()' "$work/page.html"; then
      healthy=1; break
    fi
  fi
  sleep 1
done
[[ $healthy == 1 ]]
[[ $(git rev-parse HEAD) == "$expected" ]]
clean_checkout
changed=0
printf 'DEPLOY_OK commit=%s previous=%s service=active\n' "$expected" "$previous"
completed=1
