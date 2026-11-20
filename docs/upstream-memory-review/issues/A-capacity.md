# Comment on #5320: usage against the write limit for the two built-in files

**Target:** `NousResearch/hermes-agent` · comment on the open issue #5320, not a new issue · draft only. Paste everything below the line.

---

A narrow piece of this issue, in case it is useful on its own: showing how full `MEMORY.md` and `USER.md` are, without changing any limit.

Since #145574 the Memory Layers panel names the two built-in files and the active provider. What it shows for the files is their size in bytes (`builtin_files` from `GET /api/memory`). That doesn't say how close a file is to the point where a write is refused, because the limit is in characters, counted after the entries are parsed and de-duplicated.

The change I have in mind is read-only:

- In that same panel, show each built-in file as characters used out of its configured limit, counted the way the write path counts them.
- `GET /api/memory` gains one field for this. Its existing fields stay as they are, and no route is added.
- The default limits, the write path and what goes into the prompt do not change. So this covers only the visibility part of this issue, in the Desktop; it takes no position on raising or auto-sizing the limits.

I have a prototype against `main` as of 2026-11-19. On Windows 11, 6 new backend tests pass, and so do the 119 Desktop tests in the touched areas (8 of them new). I have not run it on macOS or Linux, and I have not measured what the extra read adds to the endpoint's response time; I would measure that before opening a PR.

The prototype also lets a provider report its own store's usage through an optional read-only method. I would leave that out of a first PR unless you want it there.

Would a maintainer be open to reviewing a PR limited to this? If it doesn't belong under #5320, I can open a separate issue instead.
