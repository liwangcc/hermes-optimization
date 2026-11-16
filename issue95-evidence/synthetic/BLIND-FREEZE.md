# BLIND-FREEZE — KG-1 Stage 1 blind keywords

Freeze record for `memory/eval/blind_keywords.json`. The freeze is irreversible: no later stage may edit that file. If its sha256 ever differs from the value below, the blind set is void.

本文件是 `blind_keywords.json` 的冻结记录。冻结不可逆：之后任何阶段都不得修改该文件；sha256 与下方不一致即视为盲写集作废。

| field | value |
|---|---|
| frozen at (UTC) | `2026-11-16T09:26:48Z` |
| file | `memory/eval/blind_keywords.json` |
| sha256 | `eef343b0689afd7e356fa5e7839323e8571ee077316ca2630688682338426607` |
| entries | 30 facts, 219 keywords, 6–8 per fact |
| author | Claude (`claude-fable-5-2`), single pass, no revision after validation |

## Inputs used (exact and complete)

1. `memory/eval/facts_content_only.json` — 30 facts, `fact_id` + `content` only.
   sha256 `533b54808baeab964a088fa0779685e05da76aa1310d47c318c47d45a5faa1b8`
2. The `keywords` field description of the `fact_store` tool schema, verbatim:

   > 3-8 words or short phrases someone might use to ask for this fact that are NOT in its text: synonyms, words of another root, broader terms, and the same in the other languages the user writes in (fact 'Mom's birthday is May 3' -> birth date, anniversary, день рождения, cumpleaños). Used only to find the fact; never shown as part of it.

The only other text read before the freeze was the task contract, which contains no query text and no keywords. It supplied the format rules (3–8 per fact, zh/en crosslingual, no keyword may be a substring of its fact).

## Declaration

No evaluation queries were seen before this freeze. Specifically, none of the following was opened, searched, diffed or otherwise read before the timestamp above: `memory/eval/facts.json`, `memory/eval/queries.json`, `memory/eval/results.json`, `memory/eval/run_eval.py`, `memory/eval/README.md`, any `emb_*.npy`. No embedding run, retrieval run or score of any kind informed the keywords.

声明：冻结之前未见过任何评测查询。上述文件在冻结时间点之前均未被打开、搜索、diff 或以任何方式读取；关键词的撰写未参考任何 embedding、检索运行或得分。

## Checks at freeze time

- valid JSON object, exactly 30 entries, keys equal the 30 `fact_id`s;
- every entry has 3–8 keywords, no duplicates within an entry;
- no keyword is a substring of its fact content (checked case-insensitively, which is stricter than required).

## Verify

```sh
sha256sum memory/eval/blind_keywords.json
```

`memory/eval/.gitattributes` marks both hashed files `-text`, so git never rewrites their line endings and the hashes hold on any checkout.
