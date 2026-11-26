#!/usr/bin/env bash
# H5 (#121): the gate on the rows of run-probe.sh, with the branch's own tools/mcnemar_gate.py --pair check_margin.
# Usage: bash run-gate.sh <repo root>
set -u
ROOT=${1:?repo root}
PLUGIN=$ROOT/vendor/holo-check/plugin
HERE=$ROOT/memory/threshold-calib/upstream-check/repro
R=$HERE/rows
arms() { for s in "$@"; do echo "$R/provenance_${s}_coff_on.jsonl $R/provenance_${s}_c0.5_on.jsonl"; done; }
gate() {  # $1 receipt name, rest: sets
  local out=$HERE/$1; shift
  # shellcheck disable=SC2046
  { echo "\$ python -B tools/mcnemar_gate.py --pair check_margin $(arms "$@" | sed "s|$R/|rows/|g" | tr '\n' ' ')";
    python -B tools/mcnemar_gate.py --pair check_margin $(arms "$@"); } > "$out" 2>&1
  echo "--- $out"; cat "$out"
}
cd "$PLUGIN" || exit 1
FIVE=(multi contrast_en contrast_ru contrast_zh household_test)
gate gate-540-decisive.txt "${FIVE[@]}"                        # the test split and the sets without a split
gate gate-696-published.txt "${FIVE[@]}" household_dev synthetic_zh   # the second pool of #121 (A11)
gate gate-dev-beside.txt household_dev                         # dev alone, beside the decisive pool
gate gate-synthetic_zh-beside.txt synthetic_zh
