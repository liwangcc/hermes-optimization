---
name: task-flow-propose-first
description: "Use when a side-effecting action has an important undecided trade-off that changes the result, risk, or scope. Read-only investigation, approved plans, and unambiguous small edits do not re-confirm."
---
# Task Flow: Propose First

## Boundary
- Pure read-only investigation: just gather evidence. Unknown root cause → debugging; open design exploration → brainstorming; an approved plan → execute it.
- If the user asks you to execute directly, that is authorization. A clear goal, scope, and method need no extra plan.
- This skill only handles important undecided trade-offs; it does not own every side-effecting task.
- **A question is a consultation round, not an execution round.** "Can we / why / which is better / do you understand what I want" asks for judgment and evidence, not action. Give the conclusion, then stop and wait for an action instruction — do not casually edit files, change config, or run side-effecting commands.
- Agent instruction files (`CLAUDE.md`, `AGENTS.md`) are a protected surface: do not write them without an explicit request; if blocked, do not retry via another path or reframe the action as "just setting it up for you".
- Irreversible public publishing (posts, announcements, releases): write the text to disk first, paste it back verbatim for the user to confirm; deliver a ready-to-paste artifact and wait for the publish instruction.

## One minimal confirmation
1. Safely read the current facts, constraints, and blast radius first. Do not ask the user for paths/config/logs you can retrieve yourself. Tests are not automatically read-only — check cache, DB, network, and process side effects.
2. If goal, method, and scope are locked, execute and verify. When a reasonable choice changes the result or risk, give a recommendation plus the necessary alternatives — do not manufacture fake options.
3. Use a clarification tool if available, otherwise a plain question. **Asking a question the user must answer is the hard stop of this round**: do not keep reading new files, testing, writing, delegating, or loading another flow. Wait for the answer.
4. Empty, unselected, or unrecognizable input is still unanswered — do not guess a default. Re-ask the same decision; only refresh options read-only when external state actually changed.
5. After a choice, execute continuously within the authorized scope; do not re-ask the same decision. Pause only for a real blocker, a new important trade-off, or out-of-scope side effects.

## Verify and stop
- Check claims against real evidence: exit codes, full relevant results, exact target content, or actual behavior. Internal writes confirmed by a tool need no mechanical re-read; external system updates must be read back.
- Do not default to turning a deletion into a move / long-term archive. Confirmed-useless content authorized for deletion is deleted within scope; unconfirmed objects are kept.
- Stop when the agreed acceptance criteria are met; do not indiscriminately re-run checks or recursively dispatch reviews.