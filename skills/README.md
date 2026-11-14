# Workflow skills (lean edition)

A small set of behavioral skills for Hermes Agent. The philosophy here is deliberately
**lean**: confirm *decisions*, not *facts*; verify at runtime instead of stacking
pre-emptive rules.

> This is the distilled successor to an earlier, heavier "structured clarification"
> package. The lesson: a confirmation ritual that re-checks things the runtime can
> verify itself is overhead, not safety. Keep the human in the loop for *direction*,
> and let evidence — not ceremony — settle the rest.

## Included

| skill | purpose |
|---|---|
| `task-flow-propose-first` | Read → propose → confirm direction → execute → verify. Consultation rounds are not execution rounds. |

## Principles

- **Evidence before assertion.** A successful-looking change is not proof; read the target back.
- **Confirm decisions, not facts.** User confirmation selects a direction; it does not replace runtime verification.
- **Consultation ≠ execution.** "What do you think / which is better" asks for judgment, not action. Give the conclusion, then stop.
- **Don't manufacture options.** Decide low-stakes questions yourself; only surface genuine trade-offs.
- **Pressure-test behavioral rules.** Observe a real failure before adding a rule meant to prevent it.

## Install

Copy a skill folder into `$HERMES_HOME/skills/` (preserve the category folder), then
start a new session or run `/reload-skills`. Verify with `hermes skills list`.