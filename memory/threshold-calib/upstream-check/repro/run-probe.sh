#!/usr/bin/env bash
# H5 (#121): both arms of RECALL_CHECK_MARGIN on the seven sets, from one clean commit of the plugin branch.
# Needs the two loopback endpoints of README.md "复现端到端" (bge-m3 on 12371, Qwen3-Reranker-0.6B on 12372).
# Usage: bash run-probe.sh <repo root> [rows dir name, default rows]   (Git Bash on Windows)
set -u
ROOT=${1:?repo root}
PLUGIN=$ROOT/vendor/holo-check/plugin
HERE=$ROOT/memory/threshold-calib/upstream-check/repro
OUT=$HERE/${2:-rows}
LOG=$OUT.log
mkdir -p "$OUT"
export PYTHONIOENCODING=utf-8  # the probe's summaries print Cyrillic miss classes; the console default (GBK) garbles them
export HERMES_HOME=$ROOT/vendor/holo-check/sandbox-home   # an empty sandbox: nothing of a real install is read
export HERMES_AGENT_REPO=$ROOT/vendor/holo-check/core-e8a31a1/memory/keyword-gate/core_shim  # e8a31a1's core_shim
export EMB_URL=http://127.0.0.1:12371/v1 EMB_MODEL=bge-m3
COMMON=(--emb on --modes off --repeats 1 --endpoint http://127.0.0.1:12372/v1/rerank --out "$OUT")
CHECKED=(--recall-check-margin 0.5 --check-model Qwen/Qwen3-Reranker-0.6B --check-instruction "$HERE/instruction.txt")
LANGS=ar,bn,de,en,es,fr,hi,id,it,ja,ko,nl,pl,pt,ru,th,tr,zh
cd "$PLUGIN" || exit 1
dirty=$(git status --porcelain --untracked-files=no | wc -l)
echo "=== plugin HEAD $(git rev-parse HEAD), $dirty tracked files changed" | tee -a "$LOG"
[ "$dirty" -eq 0 ] || { echo "the plugin tree has uncommitted changes: rows would be -dirty" | tee -a "$LOG"; exit 1; }
run() {
  for arm in off checked; do
    if [ "$arm" = off ]; then extra=(--recall-check-margin off); else extra=("${CHECKED[@]}"); fi
    echo "=== $(date -u +%FT%TZ) $* ${extra[*]}" | tee -a "$LOG"
    python -B tools/provenance_probe.py "${COMMON[@]}" "$@" "${extra[@]}" >> "$LOG" 2>&1 \
      || { echo "=== FAILED: $* ($arm)" | tee -a "$LOG"; exit 1; }
  done
}
run --set multi --langs "$LANGS"
run --set contrast_en
run --set contrast_ru
run --set contrast_zh
run --set household --split test
run --set household --split dev
run --set synthetic_zh
echo "=== done $(date -u +%FT%TZ)" | tee -a "$LOG"
