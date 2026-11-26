"""Every contestant's scores side by side (results/*.json), plus how often each route ran --final (runs.log).

    python -B summarize.py            # markdown tables to stdout
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    res = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((HERE / "results").glob("*.json"))}
    for pool in ("test", "all7"):
        print(f"\n### 召回（{pool} 池，对 D0）\n")
        print("| 选手 | 命中@5 | 任意位置 | top1 | 噪声行 | 混淆行 | 追加（目标） | 追加精度 | 丢失 | b/c | p | 门禁 | cleaner |")
        print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|")
        for name, r in res.items():
            m, g = r["pools"].get(pool), r["gate"].get(pool)
            if not m:
                continue
            print(f"| {name} | {m['hit5']}/{m['answerable']} | {m['hit_any']} | {m['top1']} | {g['noise'][1]} | "
                  f"{g['confused'][1]} | {m['added']}（{m['added_target']}） | {m['added_precision']} | "
                  f"{len(g['lost_targets'])} | {g['b_rescued']}/{g['c_lost']} | {g['p']} | "
                  f"{'过' if g['passes'] else '—'} | {'是' if g.get('cleaner') else '—'} |")
        cat = {n: r for n, r in res.items() if r.get("catalog", {}).get(pool)}
        if cat:
            print(f"\n### catalog（{pool} 池）\n")
            print("| 选手 | 静态 | token/轮 | cl100k | 折算 r=0.1 | 折算 r=0.5 | B1 | label rank 中位 | 前十 |")
            print("|---|---|---:|---:|---:|---:|---:|---:|---:|")
            for name, r in cat.items():
                c = r["catalog"][pool]
                print(f"| {name} | {'是' if c['static'] else '否'} | {c['tokens_avg']} | {c['cl100k_avg']} | "
                      f"{c['effective_tokens']['r0.1']} | {c['effective_tokens']['r0.5']} | "
                      f"{c['b1_visible']}/{c['b1_missed_targets']} | {c['label_rank_median']} | {c['label_in_top10']} |")
    finals = collections.Counter()
    tuning = collections.Counter()
    log = HERE / "runs.log"
    for line in (log.read_text(encoding="utf-8").splitlines() if log.exists() else []):
        e = json.loads(line)
        route = e["name"].split("_")[0]
        (finals if e["final"] else tuning)[route] += 1
    print("\n### 调用次数（runs.log）\n")
    for route in sorted(set(finals) | set(tuning)):
        print(f"- {route}: 调参 {tuning[route]} 次，--final {finals[route]} 次")


if __name__ == "__main__":
    main()
