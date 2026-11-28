"""The pack's base rows (plugin 76689f9, 23 Nov) against the same probe arm from today's checkout:
--emb off --modes off --keywords <frozen file>. The daily version's rows were measured on that base block, so the
two must agree for the comparison with today's official rows to be about one plugin version.
Usage: python -X utf8 -B memory/recall-race/vs-official/base_check.py REPO_ROOT OUT_DIR"""
import json, os, subprocess, sys
from pathlib import Path
ROOT, OUT = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
PLUGIN = ROOT / "vendor/holo-check/plugin"
KW = PLUGIN / "tools/issue95_keywords"
RUNS = [(["--set", "contrast_en"], "contrast_en.json"), (["--set", "contrast_ru"], "contrast_ru.json"),
        (["--set", "contrast_zh"], "contrast_zh.json"), (["--set", "household", "--split", "test"], "household.json"),
        (["--set", "household", "--split", "dev"], "household.json"), (["--set", "synthetic_zh"], "synthetic_zh.json")]
env = dict(os.environ, PYTHONIOENCODING="utf-8", HERMES_HOME=str(ROOT / "vendor/holo-check/sandbox-home"),
           HERMES_AGENT_REPO=str(ROOT / "vendor/holo-check/core-e8a31a1/memory/keyword-gate/core_shim"))
OUT.mkdir(parents=True, exist_ok=True)
for args, kw in RUNS:
    cmd = [sys.executable, "-B", "tools/provenance_probe.py", "--emb", "off", "--modes", "off", "--repeats", "1",
           "--out", str(OUT), *args, "--keywords", str(KW / kw)]
    with (OUT / "run.log").open("ab") as log:
        code = subprocess.run(cmd, cwd=PLUGIN, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
    print(" ".join(args), "exit", code, flush=True)
    if code:
        raise SystemExit("probe failed: " + str(OUT / "run.log"))
old_dir = ROOT / "memory/recall-race/pack/base_rows"
same = total = 0
diff = []
for p in sorted(OUT.glob("*.jsonl")):
    new = {(r["set"], r["lang"], r["qid"]): r for r in map(json.loads, p.read_text(encoding="utf-8").splitlines())}
    old = {(r["set"], r["lang"], r["qid"]): r for r in map(json.loads, (old_dir / p.name).read_text(encoding="utf-8").splitlines())}
    for k in new:
        total += 1
        if new[k].get("keys") == old[k].get("keys"):
            same += 1
        else:
            diff.append((k, old[k].get("keys"), new[k].get("keys")))
    print(p.name, "sha", {r["git_sha"][:12] for r in new.values()})
print("rows", total, "| same facts in the same order:", same)
for d in diff[:12]:
    print("  ", d)
