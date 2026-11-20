"""Fill a throwaway HERMES_HOME with synthetic memory for the Memory Checkup demo and screenshot.

It installs the real plugins (the vendored holographic base and this repository's holographic-semantic) into that
home, writes USER.md / MEMORY.md, and stores facts through the provider's own fact_store tool, so the Desktop
screenshot and the smoke run read a store the plugin itself wrote. Everything in it is made up.

Run with the Hermes checkout's Python, from the Hermes checkout, with HERMES_HOME naming the throwaway home:

    HERMES_HOME=/path/to/sandbox python <this file> --base <holographic checkout> --adapter <holographic-semantic dir>

It refuses a home that already holds a config.yaml: it is never to be pointed at a real one.
"""

import argparse
import json
import os
import shutil
import sqlite3
import time
from pathlib import Path

USER_MD = ["The user is a backend developer in Hangzhou", "Reply in Chinese; keep code and commands in English",
           "Prefers pnpm over npm for JavaScript projects", "Works at Acme on the billing service",
           "Reviews pull requests in the morning", "Keep answers short unless asked for detail"]
MEMORY_MD = ["Config is changed through the CLI, never by patching the file", "fact#12 holds the database notes",
             "The staging cluster is called orchid"]
# (text, origin, keywords, days old, times recalled, trust, user tags)
FACTS = [
    ("The billing service database is Postgres", "said", ["database", "postgres"], 120, 0, 0.5, ""),
    ("The billing service database is PostgreSQL 16 on RDS", "said", ["database", "postgres", "version"], 45, 9, 0.8, ""),
    ("Deploys go out from the release branch on Tuesdays", "confirmed", ["deploy", "release"], 200, 14, 0.9, ""),
    ("Never deploy on Fridays", "said", ["deploy", "friday"], 300, 0, 0.6, "protected"),
    ("The user is trying out the Zed editor this week", "inferred", ["editor", "zed"], 2, 0, 0.5, ""),
    ("The staging cluster was renamed from orchid to iris in October", "said", ["staging", "cluster"], 30, 3, 0.7, ""),
    ("The on-call rotation hands over on Mondays at 10:00", "said", ["on-call", "rotation"], 90, 5, 0.7, ""),
    ("The user probably prefers tabs over spaces", "inferred", ["tabs", "indentation"], 150, 0, 0.3, ""),
    ("CI runs on self-hosted runners in the Hangzhou office", "confirmed", ["ci", "runners"], 80, 4, 0.7, ""),
    ("The invoice export job runs nightly at 02:00 UTC", "said", ["invoice", "export", "cron"], 60, 2, 0.6, ""),
    ("The Q3 migration to the new ledger finished on 2026-09-30", "said", ["migration", "ledger"], 50, 1, 0.6, ""),
    ("Use ruff for Python linting in every repository", "said", ["ruff", "lint"], 110, 7, 0.8, ""),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, help="a holographic plugin checkout (testkit pins its revision)")
    parser.add_argument("--adapter", required=True, help="memory/plugin/holographic-semantic of this repository")
    parser.add_argument("--memory-md", choices=("on", "off"), default="off", help="MEMORY.md on beside the catalog")
    parser.add_argument("--sidecar", default="", help="a sidecar address: semantic recall on, pointed there")
    args = parser.parse_args()
    home = Path(os.environ["HERMES_HOME"])
    if (home / "config.yaml").exists():
        raise SystemExit(f"{home} already has a config.yaml: point HERMES_HOME at a new, empty directory")

    ignore = shutil.ignore_patterns("__pycache__", "tests", "results", "docs", "diagram", "tools", ".git")
    shutil.copytree(args.base, home / "plugins" / "holographic", ignore=ignore)
    shutil.copytree(args.adapter, home / "plugins" / "holographic-semantic", ignore=ignore)
    (home / "memories").mkdir(parents=True)
    (home / "memories" / "USER.md").write_text("\n§\n".join(USER_MD), encoding="utf-8")
    (home / "memories" / "MEMORY.md").write_text("\n§\n".join(MEMORY_MD), encoding="utf-8")
    # By default MEMORY.md off, USER.md on, catalog on: the setup the plugin's README is written for.
    semantic = f"    semantic_enabled: true\n    semantic_url: {args.sidecar}\n" if args.sidecar else ""
    (home / "config.yaml").write_text(
        f"memory:\n  provider: holographic-semantic\n  memory_enabled: {str(args.memory_md == 'on').lower()}\n"
        "auth:\n  adopt_external_logins: false\n"
        "plugins:\n  hermes-memory-store:\n    catalog_enabled: true\n    catalog_max_tokens: 400\n" + semantic,
        encoding="utf-8")

    from plugins.memory import load_memory_provider

    provider = load_memory_provider("holographic-semantic", register_skills=False)
    if provider is None:
        raise SystemExit("Hermes could not load holographic-semantic from the sandbox home")
    provider.initialize("seed", hermes_home=str(home), platform="cli")
    ids = []
    for text, origin, keywords, *_ in FACTS:
        result = json.loads(provider.handle_tool_call(
            "fact_store", {"action": "add", "content": text, "origin": origin, "keywords": keywords}))
        if "fact_id" not in result:
            raise SystemExit(f"fact_store add refused {text!r}: {result}")
        ids.append(result["fact_id"])
    provider.shutdown()

    # Age, use and the user's tag are history the tool cannot write on request: set them on the rows.
    conn = sqlite3.connect(home / "memory_store.db")
    for fact_id, (_, _, _, days, uses, trust, tags) in zip(ids, FACTS):
        created = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() - days * 86400))
        stored = conn.execute("SELECT tags FROM facts WHERE fact_id = ?", (fact_id,)).fetchone()[0] or ""
        conn.execute("UPDATE facts SET created_at = ?, retrieval_count = ?, trust_score = ?, tags = ? WHERE fact_id = ?",
                     (created, uses, trust, f"{tags}\n{stored}" if tags else stored, fact_id))
    conn.commit()
    conn.close()
    print(json.dumps({"home": str(home), "facts": len(ids)}))


if __name__ == "__main__":
    main()
